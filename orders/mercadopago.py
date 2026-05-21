"""Mercado Pago payment-gateway service module.

MP is the ACTIVE payment gateway, replacing Culqi (which itself replaced
Izipay). Both Culqi and Izipay code is kept dormant — see settings.PAYMENT_GATEWAY.

Key points:
- Amounts are DECIMAL (S/ 100.00 is sent as 100.00, NOT 10000). Unlike Culqi,
  MP does NOT use céntimos for transaction_amount.
- Currency is always 'PEN'.
- Auth is Bearer using MERCADOPAGO_ACCESS_TOKEN — server-side only.
- Card data never reaches us: the browser tokenizes the card with MP Card
  Payment Brick and sends only a short-lived token to the backend.
- POST /v1/payments REQUIRES an X-Idempotency-Key header (UUID per request)
  so the same payment cannot be created twice on a retry.
- Webhook authenticity: HMAC-SHA256 of  id:<data.id>;request-id:<x-request-id>;ts:<ts>;
  with MERCADOPAGO_WEBHOOK_SECRET, compared against v1=<hex> in the
  x-signature header. ts is in milliseconds (string of digits) — DO NOT cast.
"""
import hmac
import hashlib
import logging
import uuid
from decimal import Decimal

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class MercadoPagoError(Exception):
    """Raised when the MP API returns an error or the request fails.

    ``user_message`` carries a Spanish, customer-safe message (e.g. a declined
    card reason); ``mp_error`` is the raw MP error object when available.
    """

    def __init__(self, message, mp_error=None):
        super().__init__(message)
        self.user_message = message
        self.mp_error = mp_error or {}


def _mp_request(
    method: str,
    path: str,
    payload: dict | None = None,
    idempotency_key: str | None = None,
    timeout: int = 30,
) -> dict:
    """Perform an authenticated MP API request and return the parsed body.

    MP returns ``{"message": "...", "error": "...", "cause": [...]}`` (with
    an HTTP 4xx) for declined cards, antifraud rejections and bad input.
    Those are surfaced as ``MercadoPagoError`` carrying the user-facing
    message.

    When ``idempotency_key`` is provided we forward it as
    ``X-Idempotency-Key``; MP guarantees POST /v1/payments will not create a
    duplicate row if the same key is replayed on a retry.
    """
    url = f'{settings.MERCADOPAGO_API_URL}{path}'
    headers = {
        'Authorization': f'Bearer {settings.MERCADOPAGO_ACCESS_TOKEN}',
        'Content-Type': 'application/json',
    }
    if idempotency_key:
        headers['X-Idempotency-Key'] = idempotency_key

    try:
        response = requests.request(method, url, json=payload, headers=headers, timeout=timeout)
    except requests.RequestException as exc:
        logger.error('Mercado Pago %s %s request failed: %s', method, path, exc)
        raise MercadoPagoError(f'Error de conexión con Mercado Pago: {exc}')

    try:
        data = response.json()
    except ValueError:
        logger.error(
            'Mercado Pago %s %s: non-JSON response (HTTP %s)',
            method, path, response.status_code,
        )
        raise MercadoPagoError('Mercado Pago devolvió una respuesta inválida.')

    # MP surfaces validation / declined-card errors as a JSON object with a
    # ``message`` field (and sometimes ``cause``/``error``) alongside the 4xx.
    if response.status_code >= 400:
        user_message = ''
        if isinstance(data, dict):
            user_message = (
                data.get('message')
                or (
                    data.get('cause', [{}])[0].get('description', '')
                    if isinstance(data.get('cause'), list) and data.get('cause')
                    else ''
                )
                or data.get('error')
                or ''
            )
        user_message = user_message or 'No se pudo procesar el pago.'
        logger.warning(
            'Mercado Pago %s %s HTTP %s: message=%s',
            method, path, response.status_code, user_message,
        )
        raise MercadoPagoError(user_message, mp_error=data if isinstance(data, dict) else {})

    return data


def _order_phone(order) -> str:
    """Best-effort phone number for MP payer details.

    MP's ``payer.phone`` is optional but useful for antifraud; we send the
    order's contact phone when one is available.
    """
    return (getattr(order, 'phone', '') or '').strip() or '999999999'


def _customer_names(order) -> tuple[str, str]:
    """Best-effort first/last name for MP payer / antifraud details.

    The Order model stores no name fields, so fall back to the associated
    User; if there is none, derive a placeholder from the order email.
    """
    user = getattr(order, 'user', None)
    email = order.email or (user.email if user else '') or 'cliente'
    first = ((user.first_name if user else '') or email.split('@')[0])[:50]
    last = ((user.last_name if user else '') or 'N/A')[:50]
    return first, last


def _notification_url() -> str:
    """Absolute URL where MP should POST webhook notifications.

    MP requires an absolute https URL; we build it from settings.DOMAIN so
    the same code works in dev (override DOMAIN in .env) and prod.
    """
    domain = (getattr(settings, 'DOMAIN', '') or '').strip()
    if not domain:
        return ''
    if domain.startswith('http://') or domain.startswith('https://'):
        return f'{domain.rstrip("/")}/pay'
    return f'https://{domain.rstrip("/")}/pay'


def create_payment(
    order,
    token: str,
    payment_method_id: str,
    issuer_id: str,
    installments: int,
    payer_email: str,
    payer_id_type: str,
    payer_id_number: str,
) -> dict:
    """Charge an MP card token for an order (synchronous, authoritative).

    The token comes from the MP Card Payment Brick in the browser and is
    already 3DS-authenticated when the issuing bank required it. MP captures
    funds in one step on ``status=approved``.

    Args:
        order:              Order instance (must expose .total, .order_number,
                            .uuid, .email).
        token:              MP card token produced by the browser Brick.
        payment_method_id:  e.g. 'visa', 'master', 'amex' — from the Brick.
        issuer_id:          MP issuer id — from the Brick. Empty string OK.
        installments:       Number of installments (1 = pago al contado).
        payer_email:        Customer email — from the Brick payer.email.
        payer_id_type:      Identification type (DNI, CE, RUC).
        payer_id_number:    Identification number.

    Returns:
        The MP payment object (dict).

    Raises:
        MercadoPagoError: If the card is declined or the API call fails. The
                          message is customer-safe and can be returned to the
                          frontend.
    """
    first, last = _customer_names(order)
    # Amount must be a JSON number with at most 2 decimal places — float() is
    # fine since order.total is a Decimal with decimal_places=2.
    transaction_amount = float(Decimal(order.total).quantize(Decimal('0.01')))

    payload: dict = {
        'transaction_amount': transaction_amount,
        'token': token,
        'description': f'Pedido {order.order_number} - Qolca Solutions'[:255],
        'installments': int(installments) if installments else 1,
        'payment_method_id': payment_method_id,
        'payer': {
            'email': payer_email or order.email or (order.user.email if order.user else ''),
            'first_name': first,
            'last_name': last,
            'phone': {
                'area_code': '',
                'number': _order_phone(order),
            },
        },
        'external_reference': f'qlca-{order.uuid}',
        'statement_descriptor': 'QOLCA',
        'metadata': {
            'order_number': order.order_number,
            'order_uuid': str(order.uuid),
            'project': 'qlca',
        },
    }
    # Issuer + identification are optional in MP's schema but the Brick
    # always provides them; include them when present.
    if issuer_id:
        payload['issuer_id'] = str(issuer_id)
    if payer_id_type and payer_id_number:
        payload['payer']['identification'] = {
            'type': payer_id_type,
            'number': payer_id_number,
        }
    notif_url = _notification_url()
    if notif_url:
        payload['notification_url'] = notif_url

    # Per-request idempotency key — guarantees retries do not create
    # duplicate payments on MP's side.
    idem = str(uuid.uuid4())
    data = _mp_request('POST', '/v1/payments', payload, idempotency_key=idem)
    logger.info(
        'Mercado Pago payment %s created for order %s (status=%s amount=%s)',
        data.get('id'), order.order_number, data.get('status'), transaction_amount,
    )
    return data


def read_payment(payment_id: str) -> dict:
    """Re-fetch a payment from MP (used to authenticate webhook events)."""
    return _mp_request('GET', f'/v1/payments/{payment_id}')


def create_refund(payment_id: str, amount: Decimal | None = None) -> dict:
    """Refund an MP payment, fully or partially.

    Pass ``amount`` for a partial refund; omit (None) for a full refund.

    Args:
        payment_id: The MP payment id to refund.
        amount:     Decimal amount in PEN; None for a full refund.

    Returns:
        The MP refund object (dict).

    Raises:
        MercadoPagoError: If the API call fails.
    """
    payload: dict | None = None
    if amount is not None:
        payload = {'amount': float(Decimal(amount).quantize(Decimal('0.01')))}

    # MP requires X-Idempotency-Key on refunds too.
    idem = str(uuid.uuid4())
    data = _mp_request(
        'POST',
        f'/v1/payments/{payment_id}/refunds',
        payload,
        idempotency_key=idem,
    )
    logger.info(
        'Mercado Pago refund created for payment %s (amount=%s)',
        payment_id, payload['amount'] if payload else 'full',
    )
    return data


def verify_webhook_signature(
    x_signature_header: str,
    x_request_id_header: str,
    data_id: str,
    secret: str,
) -> bool:
    """Verify the HMAC-SHA256 signature on an MP webhook.

    MP sends ``x-signature: ts=<digits>,v1=<hex>`` and ``x-request-id: <uuid>``.
    The signed manifest is exactly ``id:<data_id>;request-id:<x_request_id>;ts:<ts>;``
    (lowercase ``data_id`` if it is alphanumeric — MP normalises payment ids
    that way before signing).

    Returns True only when ``v1`` matches the computed digest. Any missing
    field, malformed header, or mismatching digest → False. The caller still
    returns HTTP 200 on failure (see views_mp.mp_webhook) so MP does not
    retry forever.
    """
    if not x_signature_header or not data_id or not secret:
        return False

    # Parse "ts=<digits>,v1=<hex>" — order is not guaranteed.
    ts = ''
    v1 = ''
    for part in x_signature_header.split(','):
        part = part.strip()
        if part.startswith('ts='):
            ts = part[3:].strip()
        elif part.startswith('v1='):
            v1 = part[3:].strip()

    if not ts or not v1:
        return False

    # MP normalises alphanumeric ids to lowercase before signing. Numeric
    # payment ids are unaffected by .lower() so this is safe in both cases.
    normalised_id = str(data_id).lower()
    manifest = f'id:{normalised_id};request-id:{x_request_id_header or ""};ts:{ts};'
    computed = hmac.new(
        secret.encode('utf-8'),
        manifest.encode('utf-8'),
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(computed, v1)
