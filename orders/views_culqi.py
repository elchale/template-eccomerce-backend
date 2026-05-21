"""Culqi payment API views.

Culqi is the active payment gateway (see settings.PAYMENT_GATEWAY). The Izipay
views in views_payment.py are kept registered but dormant.

Endpoints:
- POST /api/payments/culqi/charge/            — auth; charges a card/Yape token (synchronous)
- POST /api/payments/culqi/order/             — auth; creates a Culqi Order for alt methods
- POST /api/payments/culqi/webhook-<secret>/  — public; async payment notifications

Payment flow:
- Card / Yape  → the browser tokenizes the card with Culqi Checkout Custom,
  then /charge/ charges it synchronously. The charge result is authoritative.
- PagoEfectivo / wallets / Cuotéalo → /order/ creates a Culqi Order; the
  customer pays later and the order.status.changed webhook marks it paid.

Like the Izipay IPN, a received payment marks the order paid, records a
verified Payment, auto-confirms the order (e-commerce convention), clears the
cart and emails the customer. Every webhook call writes an IpnEvent audit row.
"""
import json
import logging

from django.conf import settings
from django.db import transaction
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from orders.culqi import (
    CulqiError, create_charge, create_order, read_charge, read_order,
)
from orders.email_dispatch import dispatch_order_email
from orders.models import Cart, IpnEvent, Order, OrderStatusHistory, Payment
from orders.tasks import (
    notify_admin_payment_received,
    send_payment_received_email,
)

logger = logging.getLogger(__name__)

# Max bytes to store in IpnEvent.raw_body (mirrors views_payment.RAW_BODY_MAX).
RAW_BODY_MAX = 4096


def _get_source_ip(request) -> str:
    """Extract client IP respecting X-Forwarded-For when TRUST_PROXY is True."""
    if getattr(settings, 'TRUST_PROXY', False):
        forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR', '')
        if forwarded_for:
            return forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '')


def _log_ipn_event(
    source_ip: str,
    resource_id: str,
    order_number: str,
    order_status: str,
    outcome: str,
    raw_body: str,
    error_detail: str = '',
) -> None:
    """Create a gateway-agnostic IpnEvent audit record. Never raises.

    Culqi sends no signature header, so kr_hash_prefix stores the first 8
    chars of the Culqi resource id (chr_…/ord_…) for forensic correlation.
    """
    try:
        IpnEvent.objects.create(
            gateway='culqi',
            source_ip=source_ip,
            kr_hash_prefix=resource_id[:8] if resource_id else '',
            order_number=order_number,
            order_status=order_status,
            processed_outcome=outcome,
            raw_body=raw_body[:RAW_BODY_MAX],
            error_detail=error_detail,
        )
    except Exception as exc:  # noqa: BLE001 — audit logging must never break the flow
        logger.error('Failed to create Culqi IpnEvent: %s', exc)


def _mark_order_paid(order, charge: dict) -> bool:
    """Idempotently mark an order paid from a successful Culqi charge/order.

    Mirrors the Izipay IPN PAID handler: records a verified Payment, stores the
    Culqi charge id, auto-confirms the order, clears the cart and queues the
    customer + admin emails.

    `charge` only needs `id`, `amount` and (optionally) `source.type`.

    Returns True if the order was newly marked paid, False if it was already
    paid (duplicate) — the caller uses this to choose the IpnEvent outcome
    and write the audit row.
    """
    if order.payment_status == 'paid':
        logger.info('Culqi: order %s already paid, skipping', order.order_number)
        return False

    charge_id = charge.get('id', '')
    source = charge.get('source') or {}
    payment_method = 'yape' if source.get('type') == 'yape' else 'culqi'

    paid_amount = charge.get('amount', 0)
    expected_amount = int(order.total * 100)
    if paid_amount and paid_amount != expected_amount:
        logger.error(
            'Culqi: amount mismatch for %s. Expected %d céntimos, got %d.',
            order.order_number, expected_amount, paid_amount,
        )

    # Atomic: order flags, Payment row and status history commit together, so a
    # mid-write failure can't leave payment_status='paid' with no Payment row.
    with transaction.atomic():
        order.payment_status = 'paid'
        order.culqi_charge_id = charge_id
        order.payment_method = payment_method
        order.save(update_fields=[
            'payment_status', 'culqi_charge_id', 'payment_method', 'updated',
        ])

        Payment.objects.create(
            order=order,
            method=payment_method,
            amount=order.total,
            status='verified',
            transaction_id=charge_id,
            raw_response=charge,
        )

        # Auto-confirm the order (e-commerce convention — same as Izipay IPN).
        if order.status == Order.Status.PENDING:
            old_status = order.status
            order.status = Order.Status.CONFIRMED
            order.save(update_fields=['status', 'updated'])
            OrderStatusHistory.objects.create(
                order=order,
                old_status=old_status,
                new_status=Order.Status.CONFIRMED,
                note='Auto-confirmado por pago Culqi',
                changed_by=None,
            )

        # Safety net: clear the cart (it is normally cleared at order creation).
        if order.user_id:
            cart_qs = Cart.objects.filter(user=order.user).first()
            if cart_qs:
                cart_qs.items.all().delete()

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
        'Culqi: order %s payment received (charge %s), auto-confirmed',
        order.order_number, charge_id,
    )
    return True


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_culqi_charge(request):
    """Charge a Culqi card/Yape token for a pending order owned by the user.

    Request body: { "order_uuid": "<uuid>" }  or  { "order_number": "<str>" },
                  plus { "token_id": "tkn_..." }
    Response:     { "paid": true, "order_number": "<str>", "charge_id": "<str>" }
    """
    order_uuid = (request.data.get('order_uuid') or '').strip()
    order_number = (request.data.get('order_number') or '').strip()
    token_id = (request.data.get('token_id') or '').strip()

    if not (order_uuid or order_number) or not token_id:
        return Response(
            {'detail': 'Se requieren order_uuid (u order_number) y token_id.'},
            status=400,
        )

    try:
        if order_number:
            order = Order.objects.get(order_number=order_number, user=request.user)
        else:
            order = Order.objects.get(uuid=order_uuid, user=request.user)
    except Order.DoesNotExist:
        return Response({'detail': 'Pedido no encontrado.'}, status=404)

    if order.status != Order.Status.PENDING:
        return Response({'detail': 'Este pedido ya fue procesado.'}, status=400)
    if order.payment_status == 'paid' or order.payments.filter(status='verified').exists():
        return Response({'detail': 'Este pedido ya tiene un pago verificado.'}, status=400)

    try:
        charge = create_charge(order, token_id)
    except CulqiError as exc:
        # Declined card / antifraud rejection — surface the customer-safe message.
        return Response({'detail': str(exc)}, status=402)

    _mark_order_paid(order, charge)
    return Response({
        'paid': True,
        'order_number': order.order_number,
        'charge_id': charge.get('id', ''),
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_culqi_order(request):
    """Create (or return) a Culqi Order so alternative payment methods work.

    Card / Yape do not need this — they go straight through /charge/. This is
    for PagoEfectivo, mobile wallets, bank apps and Cuotéalo.

    Request body: { "order_uuid": "<uuid>" }  or  { "order_number": "<str>" }
    Response:     { "culqi_order_id", "public_key", "amount", "currency",
                    "email", "order_number" }
    """
    order_uuid = (request.data.get('order_uuid') or '').strip()
    order_number = (request.data.get('order_number') or '').strip()
    if not (order_uuid or order_number):
        return Response(
            {'detail': 'Se requiere order_uuid u order_number.'},
            status=400,
        )

    try:
        if order_number:
            order = Order.objects.get(order_number=order_number, user=request.user)
        else:
            order = Order.objects.get(uuid=order_uuid, user=request.user)
    except Order.DoesNotExist:
        return Response({'detail': 'Pedido no encontrado.'}, status=404)

    if order.status != Order.Status.PENDING:
        return Response({'detail': 'Este pedido ya fue procesado.'}, status=400)
    if order.payment_status == 'paid':
        return Response({'detail': 'Este pedido ya está pagado.'}, status=400)

    # Reuse an existing Culqi order if one was already created — Culqi rejects
    # a duplicate order_number, and the customer may simply be retrying.
    if not order.culqi_order_id:
        try:
            culqi_order = create_order(order)
        except CulqiError as exc:
            return Response({'detail': str(exc)}, status=502)
        order.culqi_order_id = culqi_order.get('id', '')
        order.save(update_fields=['culqi_order_id', 'updated'])

    return Response({
        'culqi_order_id': order.culqi_order_id,
        'public_key': settings.CULQI_PUBLIC_KEY,
        'amount': int(order.total * 100),
        'currency': 'PEN',
        'email': order.email or (order.user.email if order.user else ''),
        'order_number': order.order_number,
    })


def _find_order(metadata: dict, culqi_order_id: str = '') -> Order | None:
    """Locate the Django order a Culqi resource belongs to.

    The Culqi account is shared with sibling projects (impresiones, etc.), so
    webhooks for their resources also arrive here. A miss is normal — the
    caller acknowledges with HTTP 200 and ignores it. ``metadata.project`` is
    tagged 'qlca' for our orders; we still self-filter by DB lookup.
    """
    metadata = metadata or {}

    order_uuid = metadata.get('order_uuid')
    if order_uuid:
        order = Order.objects.filter(uuid=order_uuid).first()
        if order:
            return order

    order_number = metadata.get('order_number')
    if order_number:
        order = Order.objects.filter(order_number=order_number).first()
        if order:
            return order

    if culqi_order_id:
        return Order.objects.filter(culqi_order_id=culqi_order_id).first()

    return None


def _handle_charge_event(charge_id: str, *, source_ip: str, raw_body: str) -> None:
    """Process a charge.* webhook event by re-fetching the charge from Culqi."""
    if not charge_id:
        return
    # Authoritative re-fetch — never trust the webhook body alone.
    charge = read_charge(charge_id)
    metadata = charge.get('metadata') or {}
    order = _find_order(metadata)
    if order is None:
        logger.info('Culqi webhook: charge %s has no matching order here', charge_id)
        _log_ipn_event(
            source_ip, charge_id, metadata.get('order_number', ''),
            'charge', 'no_order', raw_body, 'no matching order',
        )
        return
    newly_paid = _mark_order_paid(order, charge)
    _log_ipn_event(
        source_ip, charge_id, order.order_number, 'charge',
        'paid' if newly_paid else 'duplicate', raw_body,
    )


def _handle_order_event(culqi_order_id: str, *, source_ip: str, raw_body: str) -> None:
    """Process an order.status.changed webhook by re-fetching the order."""
    if not culqi_order_id:
        return
    # Authoritative re-fetch — never trust the webhook body alone.
    culqi_order = read_order(culqi_order_id)
    metadata = culqi_order.get('metadata') or {}
    state = (culqi_order.get('state') or '').lower()
    if state != 'paid':
        logger.info('Culqi webhook: order %s state=%s, no action', culqi_order_id, state)
        _log_ipn_event(
            source_ip, culqi_order_id, metadata.get('order_number', ''),
            state, 'no_op', raw_body,
        )
        return
    order = _find_order(metadata, culqi_order_id=culqi_order_id)
    if order is None:
        logger.info('Culqi webhook: order %s has no matching order here', culqi_order_id)
        _log_ipn_event(
            source_ip, culqi_order_id, metadata.get('order_number', ''),
            state, 'no_order', raw_body, 'no matching order',
        )
        return
    newly_paid = _mark_order_paid(
        order,
        {
            'id': culqi_order_id,
            'amount': culqi_order.get('amount', 0),
            'source': {'type': 'order'},
        },
    )
    _log_ipn_event(
        source_ip, culqi_order_id, order.order_number, state,
        'paid' if newly_paid else 'duplicate', raw_body,
    )


@csrf_exempt
@api_view(['POST'])
@permission_classes([AllowAny])
def culqi_webhook(request):
    """Receive Culqi webhook events. Always returns HTTP 200.

    Culqi sends no signature header, so authenticity is established by
    re-fetching the referenced resource from the Culqi API with the secret
    key (see _handle_*_event). The unguessable URL slug
    (settings.CULQI_WEBHOOK_PATH_SECRET) is a second layer of defence.

    Self-filtering: the Culqi account is shared, so events for sibling
    projects arrive here too — unknown resources are acknowledged and ignored.
    Processing is idempotent; every call writes an IpnEvent audit row.
    """
    source_ip = _get_source_ip(request)
    raw_body = (request.body or b'').decode('utf-8', errors='replace')

    try:
        event = json.loads(request.body or b'{}')
    except (json.JSONDecodeError, ValueError):
        logger.warning('Culqi webhook: invalid JSON body')
        _log_ipn_event(source_ip, '', '', '', 'bad_signature', raw_body, 'parse')
        return HttpResponse(status=200)

    event_type = event.get('type', '') or ''
    # Culqi may deliver the event wrapper ({type, data}) or the resource itself.
    data = event.get('data') or event
    resource_id = data.get('id', '') if isinstance(data, dict) else ''
    resource_object = data.get('object', '') if isinstance(data, dict) else ''

    logger.info(
        'Culqi webhook received: type=%s object=%s id=%s',
        event_type, resource_object, resource_id,
    )

    try:
        if 'charge' in event_type or resource_object == 'charge':
            _handle_charge_event(resource_id, source_ip=source_ip, raw_body=raw_body)
        elif 'order' in event_type or resource_object == 'order':
            _handle_order_event(resource_id, source_ip=source_ip, raw_body=raw_body)
        else:
            logger.info('Culqi webhook: ignored event type "%s"', event_type)
            _log_ipn_event(
                source_ip, resource_id, '', event_type,
                'no_op', raw_body, f'ignored type {event_type}',
            )
    except CulqiError as exc:
        logger.error('Culqi webhook: re-fetch failed for %s: %s', resource_id, exc)
        _log_ipn_event(
            source_ip, resource_id, '', event_type,
            'no_op', raw_body, f'refetch failed: {exc}',
        )
    except Exception as exc:  # noqa: BLE001 — must still ack with 200
        logger.error('Culqi webhook: error handling %s: %s', resource_id, exc, exc_info=True)
        _log_ipn_event(
            source_ip, resource_id, '', event_type,
            'no_op', raw_body, f'error: {exc}',
        )

    # Always 200 so Culqi does not retry; processing is idempotent.
    return HttpResponse(status=200)
