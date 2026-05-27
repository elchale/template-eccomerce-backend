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
from orders.culqi import CulqiError, create_refund as culqi_create_refund
from orders.izipay import IzipayError, cancel_or_refund
from orders.mercadopago import MercadoPagoError, create_refund as mp_create_refund
from orders.models import Cart, EmailLog, Order, OrderItem, OrderStatusHistory, Refund
from orders.serializers.orders import (
    AdminOrderRefundSerializer,
    AdminOrderSerializer,
    AdminOrderStatusUpdateSerializer,
    CheckoutSerializer,
    OrderDetailSerializer,
    OrderListSerializer,
)
from orders.tasks import send_refund_email
from orders.email_dispatch import dispatch_order_email
from orders.services.state_machine import OrderStateMachine
from orders.exceptions import InvalidTransition
from products.pricing import effective_unit_price, get_active_promo_for_product
from products.views.products import _get_active_promotions as _fetch_active_promos


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

        # Resolve active marketing promotions ONCE so each cart line is priced
        # with its applicable Promocion (batch fetch avoids N+1).
        active_promos = _fetch_active_promos()
        item_unit_price = {}
        for item in cart_items:
            promo = get_active_promo_for_product(
                item.product, active_promos=active_promos
            )
            item_unit_price[item.pk] = effective_unit_price(
                item.product, item.variant, promo
            )

        # Calculate subtotal from the promo-discounted unit prices.
        subtotal = Decimal('0.00')
        for item in cart_items:
            subtotal += item_unit_price[item.pk] * item.quantity

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
                # Immutable snapshot of what was actually charged: the
                # promo-discounted effective unit price (NOT base_price).
                price = item_unit_price[item.pk]

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

            # Clear the cart at order creation. The order is now the source
            # of truth for "what the customer is buying"; if they abandon
            # without paying they can resume payment from /orders/<n> (the
            # resume-pay CTA introduced for pending+unpaid orders), so we
            # don't need to keep the cart populated as a safety net. This
            # supersedes the older ADR §1 D5 (cart clears on IPN PAID).
            cart.items.all().delete()

        # ADR decision #1: no at-checkout confirmation email.
        # The customer's email is the payment_received notification sent
        # after the Izipay IPN confirms payment.

        return Response(
            OrderDetailSerializer(order).data,
            status=status.HTTP_201_CREATED,
        )


class OrderListView(generics.ListAPIView):
    """GET - List the authenticated user's orders.

    Supports optional `?status=` and `?payment_status=` query params so the
    storefront can ask "how many pending unpaid orders does this user have?"
    cheaply (used by the navbar's orders-icon badge).
    """

    serializer_class = OrderListSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = LimitOffsetPagination

    def get_queryset(self):
        qs = Order.objects.filter(user=self.request.user).prefetch_related('items')

        status_filter = self.request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)

        payment_status_filter = self.request.query_params.get('payment_status')
        if payment_status_filter:
            qs = qs.filter(payment_status=payment_status_filter)

        return qs


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
    """PATCH - Update order status and create history entry (admin only).

    Cancel transitions require a ``cancel_reason`` (enforced by the
    serializer). The reason is prepended to the audit note so it shows up
    verbatim in the customer-facing status history.

    Refund is intentionally NOT triggered here — cancelling a paid order
    leaves payment_status='paid' so the admin can run the gateway-side
    refund explicitly via POST /api/admin/orders/<pk>/refund/ (different
    audit trail, different failure surface).
    """

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
        cancel_reason = serializer.validated_data.get('cancel_reason', '')

        old_status = order.status

        if old_status == new_status:
            return Response(
                {'message': 'Order is already in this status.', 'type': 'invalid_transition', 'field_errors': {}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Prefix the cancel reason so it lives at the top of the audit note
        # — the customer-facing order detail surfaces this verbatim.
        combined_note = note
        if new_status == Order.Status.CANCELLED:
            prefix = f'Motivo de cancelación: {cancel_reason}'
            combined_note = f'{prefix}\n\n{note}'.strip() if note else prefix

        try:
            OrderStateMachine.transition(order, new_status, user=request.user, note=combined_note)
        except InvalidTransition as exc:
            return Response(exc.detail, status=status.HTTP_400_BAD_REQUEST)

        return Response(AdminOrderSerializer(order).data)


class AdminOrderRefundView(APIView):
    """POST /api/admin/orders/<pk>/refund/ — issue a refund via the gateway.

    Refunds via Mercado Pago when the order has an ``mp_payment_id`` (active
    gateway), else via Culqi when it has a ``culqi_charge_id`` (dormant
    gateway), else via Izipay when it has an ``izipay_transaction_id``
    (dormant gateway). This keeps both legacy Culqi-paid and Izipay-paid
    orders refundable.

    Atomic write: calls the gateway first; on success creates a Refund row,
    flips payment_status='refunded', and queues the customer email. The
    Refund row is the canonical record — admins can issue partial refunds
    by passing `amount`; omitting it refunds the order total.

    Idempotency: a paid order that's already been fully refunded is
    rejected with 400 so we don't double-charge the gateway. Partial
    refunds are allowed up to the remaining unrefunded balance.
    """

    permission_classes = [IsAdminUser]

    def post(self, request, pk):
        try:
            order = Order.objects.get(pk=pk)
        except Order.DoesNotExist:
            return Response({'detail': 'Order not found.'}, status=status.HTTP_404_NOT_FOUND)

        serializer = AdminOrderRefundSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reason = serializer.validated_data['reason']
        requested_amount = serializer.validated_data.get('amount')

        if order.payment_status != 'paid':
            return Response(
                {'detail': 'Solo se pueden reembolsar pedidos pagados.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if (
            not order.mp_payment_id
            and not order.culqi_charge_id
            and not order.izipay_transaction_id
        ):
            return Response(
                {'detail': 'El pedido no tiene una transacción de pago asociada.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Compute remaining balance (sum of processed refunds)
        already_refunded = sum(
            (r.amount for r in order.refunds.filter(status=Refund.RefundStatus.PROCESSED)),
            Decimal('0.00'),
        )
        max_refundable = order.total - already_refunded
        if max_refundable <= Decimal('0.00'):
            return Response(
                {'detail': 'Este pedido ya fue reembolsado totalmente.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        refund_amount = requested_amount if requested_amount is not None else max_refundable
        if refund_amount > max_refundable:
            return Response(
                {'detail': f'El monto excede el saldo reembolsable ({max_refundable}).'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Gateway call first — if the gateway refuses, we must not write a
        # Refund row. Mercado Pago when the order was charged via MP (active
        # gateway), else Culqi (dormant gateway) for legacy MP-era orders,
        # else Izipay (dormant gateway) for older legacy orders.
        external_refund_id = ''
        if order.mp_payment_id:
            try:
                gateway_response = mp_create_refund(
                    order.mp_payment_id, refund_amount,
                )
            except MercadoPagoError as exc:
                return Response(
                    {'detail': f'Mercado Pago rechazó el reembolso: {exc}'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            external_refund_id = (
                str(gateway_response.get('id', ''))
                if isinstance(gateway_response, dict) else ''
            )
        elif order.culqi_charge_id:
            try:
                gateway_response = culqi_create_refund(
                    order.culqi_charge_id, int(refund_amount * 100),
                )
            except CulqiError as exc:
                return Response(
                    {'detail': f'Culqi rechazó el reembolso: {exc}'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            external_refund_id = (
                gateway_response.get('id', '')
                if isinstance(gateway_response, dict) else ''
            )
        else:
            try:
                gateway_response = cancel_or_refund(
                    order.izipay_transaction_id, int(refund_amount * 100),
                )
            except IzipayError as exc:
                return Response(
                    {'detail': f'Izipay rechazó el reembolso: {exc}'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            external_refund_id = (
                gateway_response.get('answer', {}).get('transactions', [{}])[0].get('uuid', '')
                if isinstance(gateway_response, dict) else ''
            )

        with transaction.atomic():
            Refund.objects.create(
                order=order,
                amount=refund_amount,
                reason=reason,
                status=Refund.RefundStatus.PROCESSED,
                external_refund_id=external_refund_id,
                requested_by=request.user,
                processed_by=request.user,
            )

            new_remaining = max_refundable - refund_amount
            if new_remaining <= Decimal('0.00'):
                order.payment_status = 'refunded'
                order.save(update_fields=['payment_status', 'updated'])

            # Append refund event to the customer audit log so they can
            # see "Refunded: <reason>" in their own order detail page.
            OrderStatusHistory.objects.create(
                order=order,
                old_status=order.status,
                new_status=order.status,
                note=f'Reembolso ({refund_amount} {order.currency_code}): {reason}',
                changed_by=request.user,
            )

        # Fire-and-forget customer refund email via dispatch_order_email
        dispatch_order_email(
            send_refund_email,
            order.id,
            order_id=order.id,
            email_type='customer_refund',
        )

        # Re-fetch so refunds + status_history reflect the new rows
        refreshed = (
            Order.objects.select_related('user', 'coupon')
            .prefetch_related('items', 'status_history__changed_by', 'refunds')
            .get(pk=order.pk)
        )
        return Response(AdminOrderSerializer(refreshed).data)


class AdminEmailLogListView(generics.ListAPIView):
    """GET /api/admin/email-logs/ — paginated list of email logs (admin only).

    Supports optional query params:
    - status: filter by status (pending|retrying|confirmed|failed)
    - email_type: filter by EmailLog.EmailType value
    """

    permission_classes = [IsAdminUser]
    pagination_class = LimitOffsetPagination

    def get_serializer_class(self):
        from orders.serializers.email_log import EmailLogSerializer
        return EmailLogSerializer

    def get_queryset(self):
        qs = EmailLog.objects.select_related('order', 'recipient_user').all()

        status_filter = self.request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)

        email_type_filter = self.request.query_params.get('email_type')
        if email_type_filter:
            qs = qs.filter(email_type=email_type_filter)

        return qs


class AdminEmailLogRetryView(APIView):
    """POST /api/admin/email-logs/<pk>/retry/ — retry a failed or stale email log row."""

    permission_classes = [IsAdminUser]

    def post(self, request, pk):
        from orders.email_dispatch import email_log_is_retryable, retry_email_log
        from orders.serializers.email_log import EmailLogSerializer

        try:
            email_log = EmailLog.objects.select_related('order', 'recipient_user').get(pk=pk)
        except EmailLog.DoesNotExist:
            return Response({'detail': 'Email log not found.'}, status=status.HTTP_404_NOT_FOUND)

        if not email_log_is_retryable(email_log):
            return Response(
                {
                    'detail': (
                        'Este correo no se puede reintentar todavía. '
                        'Solo se reintentan los correos fallidos o los que llevan '
                        'demasiado tiempo sin enviarse.'
                    )
                },
                status=status.HTTP_409_CONFLICT,
            )

        retry_email_log(email_log)

        # Re-fetch after retry dispatch updates the row
        email_log.refresh_from_db()
        return Response(EmailLogSerializer(email_log).data, status=status.HTTP_200_OK)
