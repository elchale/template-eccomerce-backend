"""Order-on-payment checkout flow (Mercado Pago only).

The Order is created ONLY when a payment is confirmed. Until then the cart is
the durable pre-order state and a :class:`CheckoutSession` holds an immutable
snapshot of what will be charged.

Endpoints (registered in orders/urls.py):
- POST /api/checkout/pay                     — auth; create a CheckoutSession +
                                               charge an MP card token.
- GET  /api/checkout/session/<uuid>/status/  — auth, owner-only; poll status
                                               (used after a 3DS challenge).

``create_order_from_session`` is the ONLY place an Order is created. It is
atomic + idempotent and is invoked from both the synchronous /pay branch
(status=approved) and the MP webhook (covers "device died" + 3DS resolution).
"""
import logging
from decimal import Decimal

from django.db import transaction
from django.db.models import F
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from coupons.models import Coupon
from orders.email_dispatch import dispatch_order_email
from orders.mercadopago import (
    MercadoPagoError,
    create_payment,
    create_refund as mp_create_refund,
    extract_three_ds,
    resolve_status_detail,
)
from orders.models import (
    Cart,
    CheckoutSession,
    Order,
    OrderItem,
    OrderStatusHistory,
    Payment,
)
from orders.serializers.orders import CheckoutSerializer, OrderDetailSerializer
from orders.tasks import (
    notify_admin_payment_received,
    send_payment_received_email,
    send_refund_email,
)
from products.pricing import effective_unit_price, get_active_promo_for_product
from products.views.products import _get_active_promotions as _fetch_active_promos

logger = logging.getLogger(__name__)

CENTS = Decimal('0.01')


# ---------------------------------------------------------------------------
# Pricing + coupon helpers (shared by pay-init and order creation)
# ---------------------------------------------------------------------------

class CheckoutError(Exception):
    """A customer-safe checkout validation error → 400 {detail}."""

    def __init__(self, detail: str):
        super().__init__(detail)
        self.detail = detail


def _price_cart_items(cart_items) -> dict:
    """Return {cart_item_pk: promo-discounted unit price (Decimal)}.

    Resolves active marketing promotions ONCE (batch fetch avoids N+1) and
    prices each line with its applicable Promocion — identical to the legacy
    CheckoutView pricing, reused verbatim.
    """
    active_promos = _fetch_active_promos()
    item_unit_price: dict = {}
    for item in cart_items:
        promo = get_active_promo_for_product(item.product, active_promos=active_promos)
        item_unit_price[item.pk] = effective_unit_price(item.product, item.variant, promo)
    return item_unit_price


def _compute_discount(coupon, subtotal: Decimal) -> Decimal:
    """Discount amount for a (locked) coupon against a subtotal."""
    if coupon is None:
        return Decimal('0.00')
    if coupon.discount_type == Coupon.DiscountType.PERCENTAGE:
        discount = subtotal * coupon.discount_value / Decimal('100')
        if coupon.max_discount_amount is not None:
            discount = min(discount, coupon.max_discount_amount)
    else:
        discount = coupon.discount_value
    return discount


def _validate_coupon_unlocked(coupon_code: str, subtotal: Decimal) -> Coupon | None:
    """Validate a coupon code WITHOUT a row lock (pay-init pre-checks).

    Returns the Coupon (or None when no code given). Raises CheckoutError with
    a customer-safe message on any failure. Usage-limit is re-checked under a
    lock at order-creation time.
    """
    coupon_code = (coupon_code or '').strip()
    if not coupon_code:
        return None

    now = timezone.now()
    try:
        coupon = Coupon.objects.get(code__iexact=coupon_code)
    except Coupon.DoesNotExist:
        raise CheckoutError('Cupón inválido.')

    if not coupon.is_active:
        raise CheckoutError('Este cupón ya no está activo.')
    if coupon.valid_from > now or coupon.valid_until < now:
        raise CheckoutError('Este cupón expiró o aún no es válido.')
    if subtotal < coupon.min_purchase_amount:
        raise CheckoutError(
            f'Compra mínima de {coupon.min_purchase_amount} requerida para este cupón.'
        )
    if coupon.usage_limit is not None and coupon.times_used >= coupon.usage_limit:
        raise CheckoutError('Este cupón alcanzó su límite de uso.')
    return coupon


def _build_snapshot_items(cart_items, item_unit_price: dict) -> list:
    """Build the immutable JSON line-item snapshot for a CheckoutSession.

    Each entry stores the promo-discounted unit price as a string (Decimal is
    not JSON-serialisable) plus everything needed to recreate the OrderItem
    without touching the cart again at confirm time.
    """
    items = []
    for item in cart_items:
        product_images = list(item.product.images.all())
        primary_image = next((img for img in product_images if img.is_primary), None)
        image_url = ''
        if primary_image:
            image_url = primary_image.image_url
        elif item.variant and item.variant.image_url:
            image_url = item.variant.image_url
        elif product_images:
            image_url = product_images[0].image_url

        variant_info = ''
        if item.variant:
            options = list(item.variant.options.all())
            variant_info = ', '.join(
                f"{opt.variant_type.name}: {opt.value}" for opt in options
            )

        items.append({
            'product_id': item.product_id,
            'variant_id': item.variant_id,
            'product_name': item.product.name,
            'variant_info': variant_info,
            'unit_price': str(item_unit_price[item.pk].quantize(CENTS)),
            'quantity': int(item.quantity),
            'image_url': image_url,
        })
    return items


# ---------------------------------------------------------------------------
# Order creation — the ONLY place an Order is created
# ---------------------------------------------------------------------------

def _refund_and_fail(session: CheckoutSession, reason: str) -> None:
    """Refund the (already-approved) MP payment and mark the session failed.

    Used when stock is insufficient at confirm time — the payment went through
    but we cannot fulfil, so we never create an order and never oversell.
    """
    if session.mp_payment_id:
        try:
            mp_create_refund(session.mp_payment_id)
        except MercadoPagoError:
            # Refund failed — log safely (no raw MP text) and leave the
            # session failed so an admin can reconcile via IpnEvent / refunds.
            logger.error(
                'CheckoutSession %s: stock-out refund failed for payment',
                session.uuid,
            )
    CheckoutSession.objects.filter(pk=session.pk).update(
        status=CheckoutSession.Status.FAILED, updated=timezone.now(),
    )
    logger.warning('CheckoutSession %s failed at confirm: %s', session.uuid, reason)


def create_order_from_session(session: CheckoutSession) -> Order | None:
    """Create a paid Order from a confirmed CheckoutSession.

    The ONLY place an Order is created. Atomic + idempotent:
      - Guard: if the session is already paid / has an order → return it.
      - Inside transaction.atomic(): lock + DEDUCT stock, create the paid
        Order + OrderItems from the snapshot, increment coupon usage, clear
        the cart, mark the session paid, write status history.
      - Queues the customer + admin paid emails on commit.

    Stock-out edge (payment already approved): no order is created → an MP
    refund is issued + session marked failed → returns None (never oversell).
    """
    # Idempotency guard (fast path, outside the transaction).
    if session.status == CheckoutSession.Status.PAID and session.order_id:
        return session.order
    if session.order_id:
        return session.order

    from products.models import Product, ProductVariant

    try:
        with transaction.atomic():
            # Re-lock the session row so concurrent webhook + sync deliveries
            # serialise; re-check the guard under the lock. No select_related —
            # FOR UPDATE cannot be applied across the nullable order/coupon
            # outer joins (Postgres). Related rows are fetched lazily below.
            locked = (
                CheckoutSession.objects.select_for_update()
                .get(pk=session.pk)
            )
            if locked.order_id:
                return locked.order
            if locked.status == CheckoutSession.Status.PAID:
                return locked.order

            snapshot_items = locked.items or []

            # 1) Lock + DEDUCT stock from the freshly locked rows.
            for line in snapshot_items:
                qty = int(line.get('quantity', 0) or 0)
                variant_id = line.get('variant_id')
                product_id = line.get('product_id')
                name = line.get('product_name', '')
                if variant_id:
                    variant = (
                        ProductVariant.objects.select_for_update()
                        .filter(pk=variant_id)
                        .first()
                    )
                    if variant is None or qty > variant.stock:
                        available = variant.stock if variant else 0
                        _refund_and_fail(
                            locked,
                            f'insufficient stock for {name} (have {available}, need {qty})',
                        )
                        _notify_stock_out(locked)
                        return None
                    ProductVariant.objects.filter(pk=variant_id).update(
                        stock=F('stock') - qty,
                    )
                elif product_id:
                    product = (
                        Product.objects.select_for_update()
                        .filter(pk=product_id)
                        .first()
                    )
                    if product is None or qty > product.stock:
                        available = product.stock if product else 0
                        _refund_and_fail(
                            locked,
                            f'insufficient stock for {name} (have {available}, need {qty})',
                        )
                        _notify_stock_out(locked)
                        return None
                    Product.objects.filter(pk=product_id).update(
                        stock=F('stock') - qty,
                    )

            # 2) Re-validate the coupon under a row lock + recompute discount.
            coupon = None
            if locked.coupon_id:
                coupon = (
                    Coupon.objects.select_for_update()
                    .filter(pk=locked.coupon_id)
                    .first()
                )
                # If the coupon vanished or hit its limit between init and
                # confirm we still honour the charged total (the customer
                # already paid the snapshot amount) but do NOT increment usage.
                if coupon is not None and coupon.usage_limit is not None and (
                    coupon.times_used >= coupon.usage_limit
                ):
                    logger.warning(
                        'CheckoutSession %s: coupon %s over limit at confirm; '
                        'honouring charged total, not incrementing usage.',
                        locked.uuid, coupon.code,
                    )
                    coupon = None

            # 3) Create the paid Order from the snapshot.
            order = Order.objects.create(
                user=locked.user,
                status=Order.Status.CONFIRMED,
                payment_status='paid',
                payment_method='mercadopago',
                mp_payment_id=locked.mp_payment_id,
                subtotal=locked.subtotal,
                discount_amount=locked.discount_amount,
                total=locked.total,
                shipping_address=locked.shipping_address,
                billing_address=locked.billing_address,
                email=locked.email,
                phone=locked.phone,
                notes=locked.notes,
                coupon=locked.coupon if locked.coupon_id else None,
            )

            order_items = [
                OrderItem(
                    order=order,
                    product_id=line.get('product_id'),
                    variant_id=line.get('variant_id'),
                    product_name=line.get('product_name', ''),
                    variant_info=line.get('variant_info', ''),
                    price=Decimal(str(line.get('unit_price', '0'))),
                    quantity=int(line.get('quantity', 1) or 1),
                    image_url=line.get('image_url', ''),
                )
                for line in snapshot_items
            ]
            OrderItem.objects.bulk_create(order_items)

            # 4) Record the verified Payment.
            Payment.objects.create(
                order=order,
                method='mercadopago',
                amount=order.total,
                status='verified',
                transaction_id=locked.mp_payment_id,
                raw_response={'session_uuid': str(locked.uuid)},
            )

            # 5) Status history (placed + auto-confirmed by payment).
            OrderStatusHistory.objects.create(
                order=order,
                old_status=Order.Status.PENDING,
                new_status=Order.Status.CONFIRMED,
                note='Orden creada y confirmada por pago Mercado Pago.',
                changed_by=None,
            )

            # 6) Increment coupon usage (only when still valid).
            if coupon is not None:
                Coupon.objects.filter(pk=coupon.pk).update(
                    times_used=F('times_used') + 1,
                )

            # 7) Clear the cart.
            cart = Cart.objects.filter(user=locked.user).first()
            if cart:
                cart.items.all().delete()

            # 8) Mark the session paid.
            locked.status = CheckoutSession.Status.PAID
            locked.order = order
            locked.save(update_fields=['status', 'order', 'updated'])
    except Exception:
        logger.error(
            'CheckoutSession %s: order creation failed', session.uuid, exc_info=True,
        )
        raise

    # Queue async emails outside the atomic block.
    dispatch_order_email(
        send_payment_received_email,
        order.id,
        order_id=order.id,
        email_type='customer_payment_received',
    )
    dispatch_order_email(
        notify_admin_payment_received,
        order.id,
        order_id=order.id,
        email_type='admin_new_paid_order',
    )

    logger.info(
        'CheckoutSession %s confirmed → order %s created (payment %s)',
        session.uuid, order.order_number, locked.mp_payment_id,
    )
    return order


def _notify_stock_out(session: CheckoutSession) -> None:
    """Email the customer that we refunded an out-of-stock order.

    Reuses the refund-notification template; no Order exists, so we pass the
    session-derived recipient via the refund email task best-effort. A missing
    email must never break the flow.
    """
    # There is no Order to attach; the refund email task expects an order_id.
    # We therefore log + rely on the IpnEvent/admin reconciliation path. A
    # dedicated stock-out template is out of scope for this pass.
    logger.info(
        'CheckoutSession %s: customer should be notified of stock-out refund (%s)',
        session.uuid, session.email,
    )


# ---------------------------------------------------------------------------
# POST /api/checkout/pay
# ---------------------------------------------------------------------------

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def checkout_pay(request):
    """Create a CheckoutSession and charge an MP card token.

    Request body:
        {
          "shipping_address": "...", "billing_address": "...",
          "email": "...", "phone": "...", "notes": "...",
          "coupon_code": "...",
          "token": "<mp card token>", "payment_method_id": "visa",
          "issuer_id": "310", "installments": 1, "device_id": "...",
          "payer": {"email": "...", "identification": {"type": "DNI", "number": "..."}}
        }

    Responses:
      approved          → 200 OrderDetail (+ {"paid": true, "session_uuid"})
      pending_challenge → 200 {"status": "pending_challenge", "session_uuid", "three_ds"}
      in_process/pending→ 200 {"status": <s>, "session_uuid"}
      rejected/cancelled→ 402 {"detail", "code"}, cart intact, session=failed
      anti-double-charge→ 200 OrderDetail (paid session) | resume payload (processing)
    """
    serializer = CheckoutSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    token = (request.data.get('token') or '').strip()
    payment_method_id = (request.data.get('payment_method_id') or '').strip()
    issuer_id = str(request.data.get('issuer_id') or '').strip()
    try:
        installments = int(request.data.get('installments') or 1)
    except (TypeError, ValueError):
        installments = 1
    device_id = (request.data.get('device_id') or '').strip()

    payer = request.data.get('payer') or {}
    payer_email = (payer.get('email') or '').strip()
    identification = payer.get('identification') or {}
    payer_id_type = (identification.get('type') or '').strip()
    payer_id_number = (identification.get('number') or '').strip()

    if not token or not payment_method_id:
        return Response(
            {'detail': 'Se requieren token y payment_method_id.'}, status=400,
        )

    cart = Cart.objects.filter(user=request.user).first()
    cart_items = []
    if cart is not None:
        cart_items = list(
            cart.items
            .select_related('product', 'variant')
            .prefetch_related('product__images', 'variant__options__variant_type')
        )

    # --- Anti-double-charge (checked BEFORE the empty-cart guard) ---
    # If a processing session with an in-flight MP payment exists, do NOT
    # create a new payment — return its resume payload so the frontend can keep
    # polling the existing attempt (covers a re-submitted 3DS challenge).
    in_flight = (
        CheckoutSession.objects
        .filter(user=request.user, status=CheckoutSession.Status.PROCESSING)
        .exclude(mp_payment_id='')
        .order_by('-created')
        .first()
    )
    if in_flight:
        logger.info(
            'CheckoutSession %s already in-flight for user; not re-charging.',
            in_flight.uuid,
        )
        return Response({
            'status': 'processing',
            'session_uuid': str(in_flight.uuid),
        }, status=200)

    # If the cart is empty AND a recent paid session created an order, the user
    # likely re-submitted after a successful charge (e.g. the response was lost
    # / device died). Return that order instead of erroring — never re-charge.
    if not cart_items:
        paid_session = (
            CheckoutSession.objects
            .filter(
                user=request.user,
                status=CheckoutSession.Status.PAID,
                order__isnull=False,
            )
            .select_related('order')
            .order_by('-created')
            .first()
        )
        if paid_session and paid_session.order_id:
            return Response({
                'paid': True,
                'session_uuid': str(paid_session.uuid),
                **OrderDetailSerializer(paid_session.order).data,
            }, status=200)
        return Response({'detail': 'El carrito está vacío.'}, status=400)

    # Price the cart with promos and validate the coupon (unlocked pre-check).
    item_unit_price = _price_cart_items(cart_items)
    subtotal = Decimal('0.00')
    for item in cart_items:
        subtotal += item_unit_price[item.pk] * item.quantity
    subtotal = subtotal.quantize(CENTS)

    try:
        coupon = _validate_coupon_unlocked(data.get('coupon_code', ''), subtotal)
    except CheckoutError as exc:
        return Response({'detail': exc.detail}, status=400)

    discount_amount = _compute_discount(coupon, subtotal).quantize(CENTS)
    total = subtotal - discount_amount
    if total < Decimal('0.00'):
        total = Decimal('0.00')

    snapshot_items = _build_snapshot_items(cart_items, item_unit_price)

    # Create the processing session with the immutable snapshot.
    session = CheckoutSession.objects.create(
        user=request.user,
        status=CheckoutSession.Status.PROCESSING,
        email=data['email'],
        phone=data.get('phone', ''),
        shipping_address=data['shipping_address'],
        billing_address=data.get('billing_address', ''),
        notes=data.get('notes', ''),
        coupon=coupon,
        subtotal=subtotal,
        discount_amount=discount_amount,
        total=total,
        items=snapshot_items,
        gateway='mercadopago',
    )

    # Charge MP. create_payment reads .total/.uuid/.email/.order_number — we
    # pass a lightweight adapter so we don't need an Order.
    payer_resolved = (
        payer_email or session.email or (request.user.email if request.user else '')
    )
    mp_target = _SessionPaymentTarget(session, request.user, payer_resolved)

    try:
        payment = create_payment(
            mp_target,
            token=token,
            payment_method_id=payment_method_id,
            issuer_id=issuer_id,
            installments=installments,
            payer_email=payer_email,
            payer_id_type=payer_id_type,
            payer_id_number=payer_id_number,
            device_id=device_id,
            metadata_extra={'session_uuid': str(session.uuid)},
        )
    except MercadoPagoError as exc:
        # Declined / antifraud / API error — mask, fail the session, cart intact.
        CheckoutSession.objects.filter(pk=session.pk).update(
            status=CheckoutSession.Status.FAILED, updated=timezone.now(),
        )
        return Response({'detail': exc.user_message, 'code': exc.code}, status=402)

    status_value = (payment.get('status') or '').lower()
    status_detail = (payment.get('status_detail') or '').lower()
    payment_id = str(payment.get('id', ''))

    # Stash the MP payment id on the session for webhook correlation.
    if payment_id:
        session.mp_payment_id = payment_id
        session.save(update_fields=['mp_payment_id', 'updated'])

    if status_value == 'approved':
        order = create_order_from_session(session)
        if order is None:
            # Stock-out at confirm — payment was refunded, no order.
            return Response(
                {
                    'detail': (
                        'El pago se aprobó pero un producto se agotó. '
                        'Te reembolsamos el monto.'
                    ),
                    'code': 'out_of_stock',
                },
                status=409,
            )
        return Response({
            'paid': True,
            'session_uuid': str(session.uuid),
            **OrderDetailSerializer(order).data,
        }, status=201)

    if status_value == 'pending' and status_detail == 'pending_challenge':
        # 3DS challenge: NO order yet. Frontend mounts the Status Brick, then
        # polls session/status; the webhook creates the order on resolution.
        logger.info(
            'CheckoutSession %s requires 3DS challenge (payment %s)',
            session.uuid, payment_id,
        )
        return Response({
            'status': 'pending_challenge',
            'session_uuid': str(session.uuid),
            'three_ds': extract_three_ds(payment),
        }, status=200)

    if status_value in ('in_process', 'pending'):
        # Webhook will finalise — frontend polls session/status.
        return Response({
            'status': status_value,
            'session_uuid': str(session.uuid),
        }, status=200)

    if status_value in ('rejected', 'cancelled'):
        message, code = resolve_status_detail(payment.get('status_detail'))
        CheckoutSession.objects.filter(pk=session.pk).update(
            status=CheckoutSession.Status.FAILED, updated=timezone.now(),
        )
        logger.info(
            'CheckoutSession %s payment %s (code=%s)',
            session.uuid, status_value, code,
        )
        return Response({'detail': message, 'code': code}, status=402)

    # Any other status — leave processing; webhook is authoritative.
    logger.warning(
        'CheckoutSession %s returned unhandled status=%s', session.uuid, status_value,
    )
    return Response({
        'status': status_value or 'processing',
        'session_uuid': str(session.uuid),
    }, status=200)


class _SessionPaymentTarget:
    """Lightweight duck-typed adapter so ``mercadopago.create_payment`` can
    charge a CheckoutSession without an Order.

    ``create_payment`` (and its ``_build_additional_info`` helper) only read:
    ``total``, ``uuid``, ``order_number``, ``email``, ``user``, ``phone``,
    ``shipping_address`` and ``items`` (with select_related). We expose those
    from the session; ``order_number`` becomes the session reference used in
    the MP description, and ``metadata`` carries ``session_uuid`` so the
    webhook can locate the session.
    """

    def __init__(self, session: CheckoutSession, user, email: str):
        self._session = session
        self.total = session.total
        self.uuid = session.uuid
        self.order_number = f'SESS-{session.uuid}'
        self.email = email
        self.user = user
        self.phone = session.phone
        self.shipping_address = session.shipping_address

    @property
    def items(self):
        # Return a queryset-like object exposing .select_related().
        return _SnapshotItems(self._session.items or [])


class _SnapshotItems:
    """Iterable mimicking OrderItem queryset for MP additional_info building."""

    def __init__(self, snapshot: list):
        self._snapshot = snapshot

    def select_related(self, *args, **kwargs):
        return [_SnapshotItem(line) for line in self._snapshot]

    def __iter__(self):
        return iter(_SnapshotItem(line) for line in self._snapshot)


class _SnapshotItem:
    """Duck-typed OrderItem for MP additional_info (no DB access)."""

    def __init__(self, line: dict):
        self.product_id = line.get('product_id')
        self.id = line.get('product_id')
        self.product_name = line.get('product_name', '')
        self.variant_info = line.get('variant_info', '')
        self.quantity = int(line.get('quantity', 1) or 1)
        self.price = Decimal(str(line.get('unit_price', '0')))
        self.image_url = line.get('image_url', '')
        self.product = None  # category/picture enrichment is skipped (safe)


# ---------------------------------------------------------------------------
# GET /api/checkout/session/<uuid>/status/
# ---------------------------------------------------------------------------

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def checkout_session_status(request, session_uuid):
    """Return the status of a CheckoutSession (owner-only).

    Response: {"status": <processing|paid|failed|expired>, "order_number"?: str}
    Used by the frontend to poll after a 3DS challenge until the webhook
    creates the order.
    """
    session = (
        CheckoutSession.objects
        .select_related('order')
        .filter(uuid=session_uuid, user=request.user)
        .first()
    )
    if session is None:
        return Response({'detail': 'Sesión no encontrada.'}, status=404)

    body = {'status': session.status}
    if session.order_id:
        body['order_number'] = session.order.order_number
    return Response(body, status=200)
