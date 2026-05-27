"""Mercado Pago payment API views.

MP is the active payment gateway (see settings.PAYMENT_GATEWAY). The Culqi
views in views_culqi.py and the Izipay views in views_payment.py are kept
registered but dormant.

Endpoints:
- POST /api/payments/mercadopago/process/  — auth; charges an MP card token (synchronous)
- POST /pay                                — public; async payment notifications (webhook)

Payment flow:
- Card → the browser tokenizes the card with the MP Card Payment Brick (which
  also runs 3DS automatically when the issuing bank requires it), then
  /process/ creates the MP payment synchronously. The MP response is
  authoritative for status=approved; status=in_process arrives via webhook.

Like the Culqi webhook, a received payment marks the order paid, records a
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

from orders.mercadopago import (
    MercadoPagoError, create_payment, extract_three_ds, read_payment,
    resolve_status_detail, verify_webhook_signature,
)
from orders.email_dispatch import dispatch_order_email
from orders.models import Cart, IpnEvent, Order, OrderStatusHistory, Payment
from orders.tasks import (
    notify_admin_payment_received,
    send_payment_received_email,
)

logger = logging.getLogger(__name__)

# Max bytes to store in IpnEvent.raw_body (mirrors views_culqi.RAW_BODY_MAX).
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

    MP webhooks carry their own signature header; kr_hash_prefix stores the
    first 8 chars of the MP payment id (a numeric string) for forensic
    correlation, matching the convention used for Culqi.
    """
    try:
        IpnEvent.objects.create(
            gateway='mercadopago',
            source_ip=source_ip,
            kr_hash_prefix=(resource_id or '')[:8],
            order_number=order_number,
            order_status=order_status,
            processed_outcome=outcome,
            raw_body=raw_body[:RAW_BODY_MAX],
            error_detail=error_detail,
        )
    except Exception as exc:  # noqa: BLE001 — audit logging must never break the flow
        logger.error('Failed to create Mercado Pago IpnEvent: %s', exc)


def _mark_order_paid(order, payment: dict) -> bool:
    """Idempotently mark an order paid from an approved MP payment.

    Mirrors views_culqi._mark_order_paid: records a verified Payment, stores
    the MP payment id, auto-confirms the order, clears the cart and queues
    the customer + admin emails.

    ``payment`` only needs ``id`` and ``transaction_amount`` from the MP
    payment response.

    Returns True if the order was newly marked paid, False if it was already
    paid (duplicate) — the caller uses this to choose the IpnEvent outcome
    and write the audit row.
    """
    if order.payment_status == 'paid':
        logger.info('Mercado Pago: order %s already paid, skipping', order.order_number)
        return False

    payment_id = str(payment.get('id', ''))
    payment_method = 'mercadopago'

    # MP returns transaction_amount as a decimal (e.g. 100.50), not céntimos.
    paid_amount = payment.get('transaction_amount', 0) or 0
    try:
        expected_amount = float(order.total)
        if paid_amount and abs(float(paid_amount) - expected_amount) > 0.01:
            logger.error(
                'Mercado Pago: amount mismatch for %s. Expected %s, got %s.',
                order.order_number, expected_amount, paid_amount,
            )
    except (TypeError, ValueError):
        pass

    # Atomic: order flags, Payment row and status history commit together, so a
    # mid-write failure can't leave payment_status='paid' with no Payment row.
    with transaction.atomic():
        order.payment_status = 'paid'
        order.mp_payment_id = payment_id
        order.payment_method = payment_method
        order.save(update_fields=[
            'payment_status', 'mp_payment_id', 'payment_method', 'updated',
        ])

        Payment.objects.create(
            order=order,
            method=payment_method,
            amount=order.total,
            status='verified',
            transaction_id=payment_id,
            raw_response=payment,
        )

        # Auto-confirm the order (e-commerce convention — same as Culqi webhook).
        if order.status == Order.Status.PENDING:
            old_status = order.status
            order.status = Order.Status.CONFIRMED
            order.save(update_fields=['status', 'updated'])
            OrderStatusHistory.objects.create(
                order=order,
                old_status=old_status,
                new_status=Order.Status.CONFIRMED,
                note='Auto-confirmado por pago Mercado Pago',
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
        'Mercado Pago: order %s payment received (payment %s), auto-confirmed',
        order.order_number, payment_id,
    )
    return True


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_mp_payment(request):
    """Create an MP payment for a pending order owned by the user.

    Request body:
        {
          "order_uuid": "<uuid>"  or  "order_number": "<str>",
          "token": "<mp card token>",
          "payment_method_id": "visa",
          "issuer_id": "310",                # optional
          "installments": 1,
          "payer": {                          # from the Brick form data
            "email": "test@example.com",
            "identification": {"type": "DNI", "number": "12345678"}
          }
        }

    Response (status=approved): { "paid": true, "order_number": "<str>", "payment_id": "<str>", "status": "approved" }
    Response (status=in_process): { "paid": false, "order_number": "<str>", "payment_id": "<str>", "status": "in_process" }
    Response (status=rejected): HTTP 402 with translated detail.
    """
    order_uuid = (request.data.get('order_uuid') or '').strip()
    order_number = (request.data.get('order_number') or '').strip()
    token = (request.data.get('token') or '').strip()
    payment_method_id = (request.data.get('payment_method_id') or '').strip()
    issuer_id = str(request.data.get('issuer_id') or '').strip()
    installments_raw = request.data.get('installments') or 1
    try:
        installments = int(installments_raw)
    except (TypeError, ValueError):
        installments = 1

    payer = request.data.get('payer') or {}
    payer_email = (payer.get('email') or '').strip()
    identification = payer.get('identification') or {}
    payer_id_type = (identification.get('type') or '').strip()
    payer_id_number = (identification.get('number') or '').strip()
    # MP Device ID (X-meli-session-id) — improves approval rates. Optional;
    # an empty/missing value must not break the payment.
    device_id = (request.data.get('device_id') or '').strip()

    if not (order_uuid or order_number) or not token or not payment_method_id:
        return Response(
            {'detail': 'Se requieren order_uuid (u order_number), token y payment_method_id.'},
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
        payment = create_payment(
            order,
            token=token,
            payment_method_id=payment_method_id,
            issuer_id=issuer_id,
            installments=installments,
            payer_email=payer_email,
            payer_id_type=payer_id_type,
            payer_id_number=payer_id_number,
            device_id=device_id,
        )
    except MercadoPagoError as exc:
        # Declined card / antifraud rejection / API error — surface only the
        # customer-safe message + safe code. Never echo MP's raw text/code.
        return Response({'detail': exc.user_message, 'code': exc.code}, status=402)

    status_value = (payment.get('status') or '').lower()
    status_detail = (payment.get('status_detail') or '').lower()
    payment_id = str(payment.get('id', ''))

    if status_value == 'approved':
        _mark_order_paid(order, payment)
        return Response({
            'paid': True,
            'order_number': order.order_number,
            'payment_id': payment_id,
            'status': status_value,
        })

    # 3DS 2.0 challenge: MP returns status='pending' / status_detail=
    # 'pending_challenge' with a three_ds_info block. We must NOT confirm the
    # order here — the buyer still has to complete the bank challenge in the
    # Status Screen Brick. Return the challenge payload (A3 shape) so the
    # frontend can mount the Brick; the webhook (authoritative) confirms the
    # order once the challenge resolves to approved. We stash the payment id so
    # the webhook can correlate, but leave the order in its pre-payment state.
    if status_value == 'pending' and status_detail == 'pending_challenge':
        if payment_id and not order.mp_payment_id:
            order.mp_payment_id = payment_id
            order.save(update_fields=['mp_payment_id', 'updated'])
        logger.info(
            'Mercado Pago payment for order %s requires 3DS challenge (payment %s)',
            order.order_number, payment_id,
        )
        return Response({
            'status': 'pending_challenge',
            'payment_id': payment_id,
            'three_ds': extract_three_ds(payment),
        })

    if status_value in ('in_process', 'pending'):
        # The webhook will arrive shortly with the final status — stash the
        # MP payment id on the order so the webhook handler can correlate.
        if payment_id and not order.mp_payment_id:
            order.mp_payment_id = payment_id
            order.save(update_fields=['mp_payment_id', 'updated'])
        return Response({
            'paid': False,
            'order_number': order.order_number,
            'payment_id': payment_id,
            'status': status_value,
        })

    if status_value == 'rejected':
        # Map MP's raw status_detail (e.g. cc_rejected_high_risk) to a safe
        # customer message + code. NEVER echo the raw status_detail.
        message, code = resolve_status_detail(payment.get('status_detail'))
        logger.info(
            'Mercado Pago payment for order %s rejected (code=%s)',
            order.order_number, code,
        )
        return Response({'detail': message, 'code': code}, status=402)

    if status_value == 'cancelled':
        # A cancelled payment is terminal — most commonly an 'expired' 3DS
        # challenge (the buyer did not finish in time). Surface a safe, masked
        # message so the frontend can route to the error UI. NEVER echo the
        # raw status_detail.
        message, code = resolve_status_detail(payment.get('status_detail'))
        logger.info(
            'Mercado Pago payment for order %s cancelled (code=%s)',
            order.order_number, code,
        )
        return Response({'detail': message, 'code': code}, status=402)

    # Any other (refunded / charged_back / unknown) — leave the
    # order pending; webhook is authoritative.
    logger.warning(
        'Mercado Pago payment for order %s returned unhandled status=%s',
        order.order_number, status_value,
    )
    return Response({
        'paid': False,
        'order_number': order.order_number,
        'payment_id': payment_id,
        'status': status_value,
    })


def _find_order(metadata: dict) -> Order | None:
    """Locate the Django order an MP payment belongs to.

    The MP account is shared with sibling projects (impresiones, etc.), so
    webhooks for their resources also arrive here. A miss is normal — the
    caller acknowledges with HTTP 200 and ignores it. ``metadata.project`` is
    tagged 'qlca' for our orders; we still self-filter by DB lookup.
    """
    metadata = metadata or {}

    # Self-filter: only process payments tagged for this project.
    if metadata.get('project') and metadata.get('project') != 'qlca':
        return None

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

    return None


def _handle_payment_event(payment_id: str, *, source_ip: str, raw_body: str) -> None:
    """Process a payment.* webhook event by re-fetching the payment from MP."""
    if not payment_id:
        return
    # Authoritative re-fetch — never trust the webhook body alone.
    payment = read_payment(payment_id)
    metadata = payment.get('metadata') or {}
    status_value = (payment.get('status') or '').lower()

    order = _find_order(metadata)
    if order is None:
        logger.info(
            'Mercado Pago webhook: payment %s has no matching order here', payment_id,
        )
        _log_ipn_event(
            source_ip, payment_id, metadata.get('order_number', ''),
            status_value, 'no_order', raw_body, 'no matching order',
        )
        return

    if status_value != 'approved':
        logger.info(
            'Mercado Pago webhook: payment %s status=%s, no action',
            payment_id, status_value,
        )
        _log_ipn_event(
            source_ip, payment_id, order.order_number,
            status_value, 'no_op', raw_body,
        )
        return

    newly_paid = _mark_order_paid(order, payment)
    _log_ipn_event(
        source_ip, payment_id, order.order_number, status_value,
        'paid' if newly_paid else 'duplicate', raw_body,
    )


@csrf_exempt
@api_view(['POST'])
@permission_classes([AllowAny])
def mp_webhook(request):
    """Receive Mercado Pago webhook events. Always returns HTTP 200.

    Authenticity is established by:
    1. HMAC-SHA256 signature verification on the ``x-signature`` header (see
       orders.mercadopago.verify_webhook_signature). If verification fails we
       log a warning, write an IpnEvent with outcome='bad_signature', and
       acknowledge with 200 — MP otherwise retries for hours.
    2. An authoritative re-fetch via GET /v1/payments/{id} with the access
       token, then ``metadata.project == 'qlca'`` self-filtering.

    The MP account is shared with sibling projects (impresiones, etc.), so
    events for their resources arrive here too — unknown resources are
    acknowledged and ignored. Processing is idempotent; every call writes an
    IpnEvent audit row.
    """
    source_ip = _get_source_ip(request)
    raw_body = (request.body or b'').decode('utf-8', errors='replace')

    try:
        event = json.loads(request.body or b'{}')
    except (json.JSONDecodeError, ValueError):
        logger.warning('Mercado Pago webhook: invalid JSON body')
        _log_ipn_event(source_ip, '', '', '', 'bad_signature', raw_body, 'parse')
        return HttpResponse(status=200)

    event_type = (event.get('type') or event.get('action') or '') or ''
    # MP delivers {type, data:{id}, ...} for payment events. Older topic format
    # uses {topic: 'payment', resource: '<url>'} — fall back to that too.
    data = event.get('data') or {}
    resource_id = ''
    if isinstance(data, dict):
        resource_id = str(data.get('id', '') or '')
    if not resource_id and event.get('resource'):
        # Topic mode: resource is a URL ending in the payment id.
        resource_id = str(event.get('resource', '')).rstrip('/').rsplit('/', 1)[-1]

    logger.info(
        'Mercado Pago webhook received: type=%s id=%s',
        event_type, resource_id,
    )

    # 1) Signature verification. Always ack on failure (never raise).
    x_signature = request.META.get('HTTP_X_SIGNATURE', '') or request.META.get(
        'HTTP_X_SIGNATURE_V1', '',
    )
    x_request_id = request.META.get('HTTP_X_REQUEST_ID', '')
    secret = getattr(settings, 'MERCADOPAGO_WEBHOOK_SECRET', '') or ''

    if secret:
        # Only enforce the signature when the secret is configured. Without
        # a secret the integration cannot crash on signature checks — empty
        # env defaults are explicitly allowed (server must still boot).
        if not verify_webhook_signature(x_signature, x_request_id, resource_id, secret):
            logger.warning(
                'Mercado Pago webhook: signature verification failed (id=%s)',
                resource_id,
            )
            _log_ipn_event(
                source_ip, resource_id, '', event_type,
                'bad_signature', raw_body, 'signature mismatch',
            )
            return HttpResponse(status=200)

    # 2) Dispatch by event type. MP uses 'payment' (with type/action variants).
    try:
        if 'payment' in event_type.lower() or event.get('topic') == 'payment':
            _handle_payment_event(resource_id, source_ip=source_ip, raw_body=raw_body)
        else:
            logger.info('Mercado Pago webhook: ignored event type "%s"', event_type)
            _log_ipn_event(
                source_ip, resource_id, '', event_type,
                'no_op', raw_body, f'ignored type {event_type}',
            )
    except MercadoPagoError as exc:
        logger.error(
            'Mercado Pago webhook: re-fetch failed for %s: %s', resource_id, exc,
        )
        _log_ipn_event(
            source_ip, resource_id, '', event_type,
            'no_op', raw_body, f'refetch failed: {exc}',
        )
    except Exception as exc:  # noqa: BLE001 — must still ack with 200
        logger.error(
            'Mercado Pago webhook: error handling %s: %s', resource_id, exc, exc_info=True,
        )
        _log_ipn_event(
            source_ip, resource_id, '', event_type,
            'no_op', raw_body, f'error: {exc}',
        )

    # Always 200 so MP does not retry; processing is idempotent.
    return HttpResponse(status=200)
