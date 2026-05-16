"""Izipay payment API views.

Three endpoints:
- POST /api/payments/izipay/create-token/  — authenticated, returns formToken
- POST /api/payments/izipay/verify/        — authenticated, verifies client callback
- POST /api/payments/izipay/ipn/           — public, CSRF-exempt, server-to-server IPN

ADR §5 API contract. Accepts both 'sha256_hmac' and 'password' kr-hash-key
modes (matches the izipay-router and neighbour backends — our shop is
configured for legacy 'password' mode). BP2: raw kr_answer string for HMAC
verify. BP3: atomic IPN writes.
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

from orders.izipay import IzipayError, create_payment_token, verify_hash
from orders.models import Cart, IpnEvent, Order, OrderStatusHistory, Payment
from orders.tasks import (
    notify_admin_payment_received,
    send_admin_amount_mismatch_alert,
    send_payment_received_email,
    send_refund_email,
)
from orders.email_dispatch import dispatch_order_email

logger = logging.getLogger(__name__)

# Max bytes to store in IpnEvent.raw_body (BP5)
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
    kr_hash: str,
    order_number: str,
    order_status: str,
    outcome: str,
    raw_body: str,
    error_detail: str = '',
) -> IpnEvent:
    """Create an IpnEvent audit record (BP5). Always called, never raises."""
    try:
        return IpnEvent.objects.create(
            source_ip=source_ip,
            kr_hash_prefix=kr_hash[:8] if kr_hash else '',
            order_number=order_number,
            order_status=order_status,
            processed_outcome=outcome,
            raw_body=raw_body[:RAW_BODY_MAX],
            error_detail=error_detail,
        )
    except Exception as exc:
        logger.error('Failed to create IpnEvent: %s', exc)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_izipay_token(request):
    """Return an Izipay formToken for a pending order owned by the user.

    ADR §5.1 API contract.
    Request body: { "order_number": "QLCA-YYYYMMDD-XXXX" }
                  or { "order_uuid": "<uuid>" } (legacy fallback)
    Response: { "formToken": "<jwt>" }
    """
    order_number = request.data.get('order_number', '').strip()
    order_uuid = request.data.get('order_uuid', '').strip()

    if not order_number and not order_uuid:
        return Response({'detail': 'Se requiere order_number.'}, status=400)

    # Look up by order_number first, then uuid (legacy fallback)
    try:
        if order_number:
            order = Order.objects.get(order_number=order_number, user=request.user)
        else:
            order = Order.objects.get(uuid=order_uuid, user=request.user)
    except Order.DoesNotExist:
        return Response({'detail': 'Pedido no encontrado.'}, status=404)

    if order.payment_status == 'paid':
        return Response({'detail': 'Este pedido ya fue pagado.'}, status=400)

    if order.status != Order.Status.PENDING:
        return Response({'detail': 'Este pedido ya no está pendiente.'}, status=400)

    try:
        form_token = create_payment_token(order)
    except IzipayError as exc:
        return Response({'detail': f'Error de conexión con Izipay: {exc}'}, status=502)

    return Response({'formToken': form_token})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def verify_izipay_payment(request):
    """Verify a client-side payment callback signature.

    ADR §5.2 API contract. BP1: strict sha256_hmac only.
    BP2: uses raw kr_answer string, not re-serialized dict.

    Request body:
        {
            "kr_hash":     "<hex>",
            "kr_hash_key": "sha256_hmac",
            "kr_answer_raw": "<exact raw string from Krypton>"
        }

    Response: { "paid": true|false, "order_status": "PAID|UNPAID|...", "order_number": "<str>" }
    """
    kr_hash = request.data.get('kr_hash', '')
    kr_hash_key = request.data.get('kr_hash_key', '')
    kr_answer_raw = request.data.get('kr_answer_raw', None)

    # Missing raw string — fall back to IPN-as-authoritative (BP2)
    if kr_answer_raw is None:
        return Response({'paid': False, 'reason': 'no_raw'}, status=200)

    if not kr_hash or not kr_answer_raw:
        return Response(
            {'detail': 'Se requieren kr_hash y kr_answer_raw.'},
            status=400,
        )

    if kr_hash_key not in ('sha256_hmac', 'password'):
        return Response({'detail': 'Tipo de firma no soportado.'}, status=400)

    # BP2: verify against raw bytes — no re-serialization
    if not verify_hash(kr_hash, kr_answer_raw, kr_hash_key):
        return Response({'detail': 'Firma inválida.'}, status=400)

    # Parse for order_status and order_number (read-only — we do not mutate anything here)
    try:
        kr_answer = json.loads(kr_answer_raw)
    except (json.JSONDecodeError, ValueError):
        return Response({'detail': 'kr_answer_raw inválido.'}, status=400)

    order_status = kr_answer.get('orderStatus', 'UNPAID')
    order_number = kr_answer.get('orderDetails', {}).get('orderId', '')

    return Response({
        'paid': order_status == 'PAID',
        'order_status': order_status,
        'order_number': order_number,
    })


@csrf_exempt
@api_view(['POST', 'GET'])
@permission_classes([AllowAny])
def izipay_ipn(request):
    """Handle Izipay IPN webhook (server-to-server payment notification).

    ADR §5.3 / §5.4 handler logic.
    Security: CSRF-exempt + AllowAny — authentication is via HMAC-SHA-256.
    BP1: strict sha256_hmac, no fallback.
    BP3: atomic writes.
    BP5: every call creates an IpnEvent.
    """
    # GET requests are Izipay testing connectivity (liveness probe)
    if request.method == 'GET':
        return HttpResponse('OK', status=200)

    source_ip = _get_source_ip(request)

    # Step 1: IP allowlist check (empty list = allow all)
    allowed_ips = getattr(settings, 'IZIPAY_IPN_ALLOWED_IPS', [])
    if allowed_ips and source_ip not in allowed_ips:
        logger.warning('Izipay IPN: blocked IP %s not in allowlist', source_ip)
        return HttpResponse(
            json.dumps({'detail': 'IP not allowed.'}),
            content_type='application/json',
            status=403,
        )

    # Step 2: Parse body — could be JSON or form-encoded
    content_type = request.content_type or ''
    kr_hash = ''
    kr_answer_raw = ''
    kr_hash_key = ''

    if 'application/json' in content_type:
        # Read raw bytes for JSON — needed for raw_body storage and HMAC
        raw_body_bytes = request.body or b''
        raw_body_str = raw_body_bytes.decode('utf-8', errors='replace')

        try:
            body = json.loads(raw_body_bytes)
        except (json.JSONDecodeError, ValueError):
            logger.warning('Izipay IPN: invalid JSON body from %s', source_ip)
            _log_ipn_event(
                source_ip, '', '', '', 'bad_signature',
                raw_body_str, 'parse',
            )
            return HttpResponse(
                json.dumps({'detail': 'Invalid JSON body'}),
                content_type='application/json',
                status=400,
            )
        kr_hash = body.get('kr-hash', '')
        kr_answer_raw = body.get('kr-answer', '')
        kr_hash_key = body.get('kr-hash-key', '')

        # kr-answer in JSON might be a dict — convert to string for HMAC
        if isinstance(kr_answer_raw, dict):
            kr_answer_raw = json.dumps(kr_answer_raw, separators=(',', ':'))
    else:
        # Form-encoded (application/x-www-form-urlencoded)
        # DRF's FormParser populates request.data. We use it exclusively here
        # to avoid RawPostDataException (accessing request.body after request.POST
        # is already read raises an error in Django).
        parsed = request.data  # DRF FormParser already parsed this

        kr_hash = parsed.get('kr-hash', '')
        kr_answer_raw = parsed.get('kr-answer', '')
        kr_hash_key = parsed.get('kr-hash-key', '')

        # Build raw_body_str for IpnEvent (body is consumed; reconstruct from fields)
        raw_body_str = (
            f'kr-hash={kr_hash}&kr-hash-key={kr_hash_key}&kr-answer={kr_answer_raw}'
        )[:RAW_BODY_MAX]

    # Validate kr-answer is parseable before HMAC check
    if not kr_hash or not kr_answer_raw:
        _log_ipn_event(
            source_ip, kr_hash, '', '', 'bad_signature',
            raw_body_str, 'missing_fields',
        )
        return HttpResponse(
            json.dumps({'detail': 'Missing required fields'}),
            content_type='application/json',
            status=400,
        )

    # Parse kr_answer string to dict (needed after HMAC check)
    try:
        if isinstance(kr_answer_raw, str):
            kr_answer = json.loads(kr_answer_raw)
        else:
            kr_answer = kr_answer_raw
            kr_answer_raw = json.dumps(kr_answer_raw, separators=(',', ':'))
    except (json.JSONDecodeError, ValueError):
        _log_ipn_event(
            source_ip, kr_hash, '', '', 'bad_signature',
            raw_body_str, 'parse_kr_answer',
        )
        return HttpResponse(
            json.dumps({'detail': 'Could not parse kr-answer'}),
            content_type='application/json',
            status=400,
        )

    order_number = kr_answer.get('orderDetails', {}).get('orderId', '')
    order_status = kr_answer.get('orderStatus', '')

    # Step 3: accept both supported modes — anything else is malformed.
    # The router and neighbour backends do the same; our Izipay shop signs
    # in legacy 'password' mode.
    if kr_hash_key not in ('sha256_hmac', 'password'):
        logger.warning(
            'Izipay IPN: wrong kr-hash-key type "%s" from %s',
            kr_hash_key, source_ip,
        )
        _log_ipn_event(
            source_ip, kr_hash, order_number, order_status,
            'bad_signature', raw_body_str, 'wrong_key',
        )
        return HttpResponse(
            json.dumps({'detail': 'Tipo de firma no soportado.'}),
            content_type='application/json',
            status=400,
        )

    # Step 4: Re-verify HMAC (defense-in-depth — router already verified)
    if not verify_hash(kr_hash, kr_answer_raw, kr_hash_key):
        logger.warning(
            'Izipay IPN: HMAC mismatch from %s for order %s',
            source_ip, order_number,
        )
        _log_ipn_event(
            source_ip, kr_hash, order_number, order_status,
            'bad_signature', raw_body_str, 'hmac_mismatch',
        )
        return HttpResponse(
            json.dumps({'detail': 'Firma inválida.'}),
            content_type='application/json',
            status=400,
        )

    # Steps 5-10: Order lookup + checks + writes inside a single atomic block
    # with select_for_update to close the concurrent-PAID race window.
    # If two PAID IPNs arrive for the same order, one blocks on the row lock;
    # by the time it runs, the first has already set payment_status='paid' and
    # the idempotency check below catches it.
    with transaction.atomic():
        try:
            order = Order.objects.select_for_update().get(order_number=order_number)
        except Order.DoesNotExist:
            logger.error('Izipay IPN: order %s not found', order_number)
            _log_ipn_event(
                source_ip, kr_hash, order_number, order_status,
                'no_order', raw_body_str, f'order_number={order_number}',
            )
            return HttpResponse(
                json.dumps({'status': 'ok'}),
                content_type='application/json',
                status=200,
            )

        # Idempotency guard — PAID + already paid
        if order.payment_status == 'paid' and order_status == 'PAID':
            logger.info(
                'Izipay IPN: duplicate PAID for order %s, skipping',
                order_number,
            )
            _log_ipn_event(
                source_ip, kr_hash, order_number, order_status,
                'duplicate', raw_body_str,
            )
            return HttpResponse(
                json.dumps({'status': 'ok'}),
                content_type='application/json',
                status=200,
            )

        # Amount check for PAID IPNs (BP4)
        if order_status == 'PAID':
            paid_amount = kr_answer.get('orderDetails', {}).get('orderTotalAmount', 0)
            expected_amount = int(order.total * 100)

            if paid_amount != expected_amount:
                logger.error(
                    'Izipay IPN: amount mismatch for %s — expected %d, got %d centimos',
                    order_number, expected_amount, paid_amount,
                )
                _log_ipn_event(
                    source_ip, kr_hash, order_number, order_status,
                    'bad_amount', raw_body_str,
                    f'expected={expected_amount} received={paid_amount}',
                )
                dispatch_order_email(
                    send_admin_amount_mismatch_alert,
                    order.id, expected_amount, paid_amount,
                    order_id=order.id,
                    email_type='admin_amount_mismatch',
                )
                # Return 200 — do NOT mark paid (tamper detection)
                return HttpResponse(
                    json.dumps({'status': 'ok'}),
                    content_type='application/json',
                    status=200,
                )

        if order_status == 'PAID':
            transactions = kr_answer.get('transactions', [])
            tx = transactions[0] if transactions else {}
            tx_uuid = tx.get('uuid', '')

            # D3: Yape mapping
            tx_method_type = tx.get('paymentMethodType', '')
            payment_method = 'yape' if tx_method_type == 'E_WALLET' else 'izipay'

            order.payment_status = 'paid'
            order.izipay_transaction_id = tx_uuid
            order.payment_method = payment_method
            order.save(update_fields=[
                'payment_status', 'izipay_transaction_id', 'payment_method', 'updated',
            ])

            Payment.objects.create(
                order=order,
                method=payment_method,
                amount=order.total,
                status='verified',
                transaction_id=tx_uuid,
                raw_response=tx,
            )

            # BP6: Auto-confirm order (e-commerce convention)
            old_status = order.status
            order.status = Order.Status.CONFIRMED
            order.save(update_fields=['status', 'updated'])
            OrderStatusHistory.objects.create(
                order=order,
                old_status=old_status,
                new_status=Order.Status.CONFIRMED,
                note='Auto-confirmado por pago Izipay',
                changed_by=None,
            )

            # Cart was cleared at order creation (CheckoutView); this branch
            # is now a safety net for orders created before that change. The
            # delete is idempotent so it's safe even if the cart is already
            # empty.
            cart_qs = Cart.objects.filter(user=order.user).first()
            if cart_qs:
                cart_qs.items.all().delete()

            _log_ipn_event(
                source_ip, kr_hash, order_number, order_status,
                'paid', raw_body_str,
            )

        elif order_status == 'REFUNDED':
            order.payment_status = 'refunded'
            order.save(update_fields=['payment_status', 'updated'])

            _log_ipn_event(
                source_ip, kr_hash, order_number, order_status,
                'refunded', raw_body_str,
            )

        elif order_status == 'CANCELLED':
            order.payment_status = 'refunded'
            order.save(update_fields=['payment_status', 'updated'])

            _log_ipn_event(
                source_ip, kr_hash, order_number, order_status,
                'cancelled', raw_body_str,
            )

        elif order_status == 'UNPAID':
            # No-op — customer can retry payment
            _log_ipn_event(
                source_ip, kr_hash, order_number, order_status,
                'unpaid', raw_body_str,
            )

        else:
            logger.info(
                'Izipay IPN: unhandled order_status=%s for order %s',
                order_status, order_number,
            )
            _log_ipn_event(
                source_ip, kr_hash, order_number, order_status,
                'no_op', raw_body_str, order_status,
            )

    # Queue async tasks outside the atomic block via dispatch_order_email
    if order_status == 'PAID':
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
        # Cart was already cleared inside the atomic block (D5)
    elif order_status in ('REFUNDED', 'CANCELLED'):
        dispatch_order_email(
            send_refund_email,
            order.id,
            order_id=order.id,
            email_type='customer_refund',
        )

    return HttpResponse(
        json.dumps({'status': 'ok'}),
        content_type='application/json',
        status=200,
    )
