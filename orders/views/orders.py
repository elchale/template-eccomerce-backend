from decimal import Decimal

from django.db import transaction
from django.db.models import F
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.pagination import LimitOffsetPagination
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from coupons.models import Coupon
from orders.izipay import IzipayError, cancel_or_refund
from orders.models import Cart, Order, OrderItem, OrderStatusHistory
from orders.serializers.orders import (
    AdminOrderSerializer,
    AdminOrderStatusUpdateSerializer,
    CheckoutSerializer,
    OrderDetailSerializer,
    OrderListSerializer,
)
from orders.tasks import send_order_confirmation_email
from orders.services.state_machine import OrderStateMachine
from orders.exceptions import InvalidTransition


class CheckoutView(APIView):
    """POST - Create an order from the user's cart."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = CheckoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        # Get the user's cart
        try:
            cart = Cart.objects.prefetch_related(
                'items__product', 'items__variant'
            ).get(user=request.user)
        except Cart.DoesNotExist:
            return Response(
                {'detail': 'Cart not found.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        cart_items = list(
            cart.items
            .select_related('product', 'variant')
            .prefetch_related('product__images', 'variant__options__variant_type')
        )
        if not cart_items:
            return Response(
                {'detail': 'Cart is empty.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Calculate subtotal
        subtotal = Decimal('0.00')
        for item in cart_items:
            price = item.variant.price if item.variant else item.product.base_price
            subtotal += price * item.quantity

        # Validate coupon format if provided (pre-atomic checks only)
        coupon_code = data.get('coupon_code', '').strip()
        if coupon_code:
            now = timezone.now()
            try:
                _coupon_check = Coupon.objects.get(code__iexact=coupon_code)
            except Coupon.DoesNotExist:
                return Response(
                    {'detail': 'Invalid coupon code.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if not _coupon_check.is_active:
                return Response(
                    {'detail': 'This coupon is no longer active.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if _coupon_check.valid_from > now or _coupon_check.valid_until < now:
                return Response(
                    {'detail': 'This coupon has expired or is not yet valid.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if subtotal < _coupon_check.min_purchase_amount:
                return Response(
                    {'detail': f'Minimum purchase of ${_coupon_check.min_purchase_amount} required for this coupon.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        with transaction.atomic():
            # --- BE-1: Coupon race condition fix ---
            # Re-fetch coupon with SELECT FOR UPDATE inside the atomic block so
            # concurrent checkouts cannot both pass the usage_limit check.
            coupon = None
            discount_amount = Decimal('0.00')

            if coupon_code:
                now = timezone.now()
                try:
                    coupon = Coupon.objects.select_for_update().get(
                        code__iexact=coupon_code
                    )
                except Coupon.DoesNotExist:
                    return Response(
                        {'detail': 'Invalid coupon code.'},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                # Re-check usage limit AFTER acquiring the row lock
                if coupon.usage_limit is not None and coupon.times_used >= coupon.usage_limit:
                    return Response(
                        {'detail': 'This coupon has reached its usage limit.'},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                # Calculate discount
                if coupon.discount_type == Coupon.DiscountType.PERCENTAGE:
                    discount_amount = subtotal * coupon.discount_value / Decimal('100')
                    if coupon.max_discount_amount is not None:
                        discount_amount = min(discount_amount, coupon.max_discount_amount)
                else:
                    discount_amount = coupon.discount_value

            total = subtotal - discount_amount
            if total < Decimal('0.00'):
                total = Decimal('0.00')

            # --- BE-2: Stock race condition fix ---
            # Re-fetch each variant/product with SELECT FOR UPDATE before checking stock.
            # Read stock from the freshly locked row, not from the cached cart relation.
            for item in cart_items:
                if item.variant:
                    variant = item.variant.__class__.objects.select_for_update().get(
                        pk=item.variant.pk
                    )
                    if item.quantity > variant.stock:
                        return Response(
                            {'detail': f'Insufficient stock for {item.product.name} ({variant.sku}). Only {variant.stock} available.'},
                            status=status.HTTP_400_BAD_REQUEST,
                        )
                    variant.stock = F('stock') - item.quantity
                    variant.save(update_fields=['stock'])
                else:
                    product = item.product.__class__.objects.select_for_update().get(
                        pk=item.product.pk
                    )
                    if item.quantity > product.stock:
                        return Response(
                            {'detail': f'Insufficient stock for {item.product.name}. Only {product.stock} available.'},
                            status=status.HTTP_400_BAD_REQUEST,
                        )
                    product.stock = F('stock') - item.quantity
                    product.save(update_fields=['stock'])

            # Create order — order_number generated by Order.save() (model override, ADR §6.4)
            order = Order.objects.create(
                user=request.user,
                status=Order.Status.PENDING,
                subtotal=subtotal,
                discount_amount=discount_amount,
                total=total,
                shipping_address=data['shipping_address'],
                billing_address=data.get('billing_address', ''),
                email=data['email'],
                phone=data.get('phone', ''),
                notes=data.get('notes', ''),
                coupon=coupon,
            )

            # Create order items with snapshot data
            order_items = []
            for item in cart_items:
                price = item.variant.price if item.variant else item.product.base_price

                # Get product image using prefetched data to avoid N+1 queries.
                product_images = list(item.product.images.all())
                primary_image = next(
                    (img for img in product_images if img.is_primary), None
                )
                image_url = ''
                if primary_image:
                    image_url = primary_image.image_url
                elif item.variant and item.variant.image_url:
                    image_url = item.variant.image_url
                elif product_images:
                    image_url = product_images[0].image_url

                # Build variant info string using prefetched options.
                variant_info = ''
                if item.variant:
                    options = list(item.variant.options.all())
                    variant_info = ', '.join(
                        f"{opt.variant_type.name}: {opt.value}" for opt in options
                    )

                order_items.append(
                    OrderItem(
                        order=order,
                        product=item.product,
                        variant=item.variant,
                        product_name=item.product.name,
                        variant_info=variant_info,
                        price=price,
                        quantity=item.quantity,
                        image_url=image_url,
                    )
                )

            OrderItem.objects.bulk_create(order_items)

            # Create initial status history
            OrderStatusHistory.objects.create(
                order=order,
                old_status=Order.Status.PENDING,
                new_status=Order.Status.PENDING,
                note='Order placed.',
                changed_by=request.user,
            )

            # Increment coupon usage
            if coupon:
                Coupon.objects.filter(pk=coupon.pk).update(
                    times_used=F('times_used') + 1
                )

            # ADR §1 D5: cart clears on IPN PAID, not at order creation.
            # Do NOT clear cart here — preserved so abandoned-cart users can return.

        # Send confirmation email via Celery
        send_order_confirmation_email.delay(order.id)

        return Response(
            OrderDetailSerializer(order).data,
            status=status.HTTP_201_CREATED,
        )


class OrderListView(generics.ListAPIView):
    """GET - List the authenticated user's orders."""

    serializer_class = OrderListSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Order.objects.filter(user=self.request.user).prefetch_related('items')


class OrderDetailView(generics.RetrieveAPIView):
    """GET - Retrieve a single order by order_number (owner only)."""

    serializer_class = OrderDetailSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = 'order_number'

    def get_queryset(self):
        return Order.objects.filter(
            user=self.request.user
        ).prefetch_related('items', 'status_history__changed_by')


class AdminOrderListView(generics.ListAPIView):
    """GET - List all orders (admin only). Filterable by status."""

    serializer_class = AdminOrderSerializer
    permission_classes = [IsAdminUser]
    pagination_class = LimitOffsetPagination

    def get_queryset(self):
        queryset = Order.objects.select_related(
            'user', 'coupon'
        ).prefetch_related(
            'items', 'status_history__changed_by'
        ).all()

        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        return queryset


class AdminOrderDetailView(generics.RetrieveAPIView):
    """GET - Retrieve a single order by ID (admin only)."""

    serializer_class = AdminOrderSerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        return Order.objects.select_related(
            'user', 'coupon'
        ).prefetch_related(
            'items', 'status_history__changed_by'
        ).all()


class AdminOrderStatusUpdateView(APIView):
    """PATCH - Update order status and create history entry (admin only)."""

    permission_classes = [IsAdminUser]

    def patch(self, request, pk):
        try:
            order = Order.objects.get(pk=pk)
        except Order.DoesNotExist:
            return Response(
                {'detail': 'Order not found.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = AdminOrderStatusUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        new_status = serializer.validated_data['new_status']
        note = serializer.validated_data.get('note', '')

        old_status = order.status

        if old_status == new_status:
            return Response(
                {'message': 'Order is already in this status.', 'type': 'invalid_transition', 'field_errors': {}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # When admin cancels a paid order, attempt refund via Izipay before state transition
        if new_status == 'cancelled' and order.payment_status == 'paid' and order.izipay_transaction_id:
            try:
                cancel_or_refund(order.izipay_transaction_id, int(order.total * 100))
            except IzipayError as exc:
                return Response(
                    {'message': f'Refund failed: {exc}', 'type': 'refund_failed', 'field_errors': {}},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            order.payment_status = 'refunded'
            order.save(update_fields=['payment_status', 'updated'])

        try:
            OrderStateMachine.transition(order, new_status, user=request.user, note=note)
        except InvalidTransition as exc:
            return Response(exc.detail, status=status.HTTP_400_BAD_REQUEST)

        return Response(AdminOrderSerializer(order).data)
