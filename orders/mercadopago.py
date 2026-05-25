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


# Maps MP status_detail -> (customer-safe Spanish message, safe category code).
# Fraud reasons (high_risk, blacklist) are deliberately masked.
_STATUS_DETAIL_MAP: dict[str, tuple[str, str]] = {
    # approved / pending
    'accredited': ('Pago aprobado.', 'approved'),
    'pending_contingency': ('Estamos procesando tu pago. Te confirmaremos por correo en unos minutos.', 'processing'),
    'pending_review_manual': ('Estamos revisando tu pago. Te confirmaremos por correo dentro de 2 días hábiles.', 'pending_review'),
    'pending_waiting_payment': ('Estamos esperando la confirmación de tu pago.', 'processing'),
    'pending_challenge': ('Completa la verificación de seguridad de tu banco para confirmar el pago.', 'needs_action'),
    # fixable card-data errors (keep the form open so the user can correct)
    'cc_rejected_bad_filled_card_number': ('Revisa el número de tarjeta e intenta de nuevo.', 'card_data_invalid'),
    'cc_rejected_bad_filled_date': ('Revisa la fecha de vencimiento de la tarjeta.', 'card_data_invalid'),
    'cc_rejected_bad_filled_security_code': ('Revisa el código de seguridad (CVV) de la tarjeta.', 'card_data_invalid'),
    'cc_rejected_bad_filled_other': ('Revisa los datos de la tarjeta e intenta de nuevo.', 'card_data_invalid'),
    'rejected_insufficient_data': ('Faltan datos para procesar el pago. Revisa la información e intenta de nuevo.', 'card_data_invalid'),
    # declines (suggest another card / method)
    'cc_rejected_insufficient_amount': ('Tu tarjeta no tiene saldo suficiente. Intenta con otra.', 'insufficient_funds'),
    'cc_rejected_call_for_authorize': ('Tu banco debe autorizar el pago. Llama al número en el reverso de tu tarjeta y vuelve a intentar.', 'needs_bank_auth'),
    'cc_rejected_card_disabled': ('Tu tarjeta está inactiva. Llama a tu banco para activarla e intenta de nuevo.', 'needs_bank_auth'),
    'cc_rejected_card_error': ('No pudimos procesar tu tarjeta. Intenta con otra.', 'declined'),
    'cc_rejected_duplicated_payment': ('Ya registramos un pago por este monto. Si necesitas pagar otra vez, usa otra tarjeta o espera unos minutos.', 'duplicate'),
    'cc_rejected_invalid_installments': ('Tu tarjeta no permite esa cantidad de cuotas. Elige otra opción.', 'declined'),
    'cc_rejected_max_attempts': ('Alcanzaste el límite de intentos. Usa otra tarjeta o intenta más tarde.', 'max_attempts'),
    'cc_rejected_other_reason': ('Tu banco rechazó el pago. Intenta con otra tarjeta o comunícate con tu banco.', 'declined'),
    'cc_rejected_3ds_mandatory': ('Debes completar la verificación de seguridad (3DS) de tu banco para continuar.', 'needs_action'),
    'cc_amount_rate_limit_exceeded': ('El monto supera el límite de tu tarjeta. Intenta con otra.', 'declined'),
    'rejected_by_bank': ('Tu banco rechazó la transacción. Comunícate con tu banco para más detalles.', 'declined'),
    'rejected_by_regulations': ('No pudimos procesar este pago. Intenta con otro medio de pago.', 'declined'),
    # fraud — MASKED (never reveal the reason)
    'cc_rejected_high_risk': ('Por seguridad, tu pago fue rechazado. Intenta con otro medio de pago.', 'declined'),
    'cc_rejected_blacklist': ('No pudimos procesar tu pago. Intenta con otro medio de pago.', 'declined'),
}

# Generic fallback for unknown codes, API errors, and connection failures.
_GENERIC_MESSAGE = 'No pudimos procesar tu pago. Intenta de nuevo o escríbenos a info@qolca.org.'
_GENERIC_CODE = 'generic'


def resolve_status_detail(status_detail: str | None) -> tuple[str, str]:
    """Return (customer-safe message, safe code) for an MP status_detail.

    Unknown codes fall back to the generic message — we never return the raw
    MP code or MP's own message to the client.
    """
    if status_detail and status_detail in _STATUS_DETAIL_MAP:
        return _STATUS_DETAIL_MAP[status_detail]
    return (_GENERIC_MESSAGE, _GENERIC_CODE)


class MercadoPagoError(Exception):
    """Raised when the MP API returns an error or the request fails.

    ``user_message`` carries a Spanish, customer-safe message (e.g. a declined
    card reason); ``mp_error`` is the raw MP error object when available;
    ``code`` is a safe category code (never a raw MP code).
    """

    def __init__(self, message, mp_error=None, code='generic'):
        super().__init__(message)
        self.user_message = message
        self.mp_error = mp_error or {}
        self.code = code


def _mp_request(
    method: str,
    path: str,
    payload: dict | None = None,
    idempotency_key: str | None = None,
    device_id: str | None = None,
    timeout: int = 30,
) -> dict:
    """Perform an authenticated MP API request and return the parsed body.

    MP returns ``{"message": "...", "error": "...", "cause": [...]}`` (with
    an HTTP 4xx) for declined cards, antifraud rejections and bad input.
    Those are surfaced as ``MercadoPagoError`` carrying a customer-SAFE
    message (mapped from ``status_detail`` when present) — MP's raw text is
    never exposed to the client.

    When ``idempotency_key`` is provided we forward it as
    ``X-Idempotency-Key``; MP guarantees POST /v1/payments will not create a
    duplicate row if the same key is replayed on a retry.

    When ``device_id`` is provided we forward it as ``X-meli-session-id`` —
    MP's antifraud fingerprint that materially cuts ``high_risk`` rejections.
    A missing/empty device id simply omits the header (never breaks the call).
    """
    url = f'{settings.MERCADOPAGO_API_URL}{path}'
    headers = {
        'Authorization': f'Bearer {settings.MERCADOPAGO_ACCESS_TOKEN}',
        'Content-Type': 'application/json',
    }
    if idempotency_key:
        headers['X-Idempotency-Key'] = idempotency_key
    if device_id:
        headers['X-meli-session-id'] = device_id

    try:
        response = requests.request(method, url, json=payload, headers=headers, timeout=timeout)
    except requests.RequestException as exc:
        # Do not log the raw exception text (may echo URL/secrets in transit).
        logger.error('Mercado Pago %s %s request failed (connection)', method, path)
        raise MercadoPagoError(_GENERIC_MESSAGE, code=_GENERIC_CODE)

    try:
        data = response.json()
    except ValueError:
        logger.error(
            'Mercado Pago %s %s: non-JSON response (HTTP %s)',
            method, path, response.status_code,
        )
        raise MercadoPagoError(_GENERIC_MESSAGE, code=_GENERIC_CODE)

    # MP surfaces validation / declined-card errors as a JSON object with a
    # ``status_detail`` (and ``message``/``cause``/``error``) alongside the
    # 4xx. We map status_detail to a safe message + code; MP's raw text is
    # kept only in ``mp_error`` for server-side logging.
    if response.status_code >= 400:
        status_detail = ''
        if isinstance(data, dict):
            status_detail = data.get('status_detail') or ''
        if status_detail:
            user_message, code = resolve_status_detail(status_detail)
        else:
            user_message, code = _GENERIC_MESSAGE, _GENERIC_CODE
        # Log only HTTP status + safe code — never MP's raw message/cause.
        logger.warning(
            'Mercado Pago %s %s HTTP %s: code=%s',
            method, path, response.status_code, code,
        )
        raise MercadoPagoError(
            user_message,
            mp_error=data if isinstance(data, dict) else {},
            code=code,
        )

    return data


def _payer_phone(order) -> str:
    """Real contact phone for MP antifraud, or '' if none.

    MP's ``payer.phone`` is optional; we only send a real, non-empty value.
    No placeholder fallback — an absent phone is omitted entirely.
    """
    phone = (getattr(order, 'phone', '') or '').strip()
    if phone:
        return phone
    user = getattr(order, 'user', None)
    return (getattr(user, 'phone', '') or '').strip() if user else ''


def _customer_names(order) -> tuple[str, str]:
    """Real first/last name from the associated User, or ('', '').

    No placeholders: callers must skip empty names rather than send 'N/A'.
    """
    user = getattr(order, 'user', None)
    if not user:
        return '', ''
    return (getattr(user, 'first_name', '') or '')[:50], (getattr(user, 'last_name', '') or '')[:50]


def _build_additional_info(order) -> dict:
    """Build MP ``additional_info`` from real order data for antifraud scoring.

    Includes line items, the payer's real name/phone/registration_date (only
    when present), and a shipping receiver_address when the order has one.
    Empty/placeholder values are omitted rather than faked.
    """
    info: dict = {}

    items = []
    for item in order.items.all():
        entry: dict = {
            'id': str(item.product_id or item.id),
            'title': (item.product_name or '')[:256],
            'quantity': int(item.quantity or 1),
            'unit_price': float(Decimal(item.price).quantize(Decimal('0.01'))),
        }
        if item.variant_info:
            entry['description'] = item.variant_info[:256]
        items.append(entry)
    if items:
        info['items'] = items

    # payer block — only real values.
    payer: dict = {}
    first, last = _customer_names(order)
    if first:
        payer['first_name'] = first
    if last:
        payer['last_name'] = last
    phone = _payer_phone(order)
    if phone:
        payer['phone'] = {'area_code': '51', 'number': phone}
    user = getattr(order, 'user', None)
    if user and getattr(user, 'date_joined', None):
        payer['registration_date'] = user.date_joined.isoformat()
    if payer:
        info['payer'] = payer

    # shipments.receiver_address — only when the order carries a real shipping
    # address. The Order model stores it as free text, so we map the fields we
    # can confidently extract (zip omitted when blank, etc.).
    shipping = (getattr(order, 'shipping_address', '') or '').strip()
    if shipping:
        receiver: dict = {'street_name': shipping[:256]}
        info['shipments'] = {'receiver_address': receiver}

    return info


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
    device_id: str | None = None,
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
        device_id:          MP Device ID (X-meli-session-id) from the browser
                            security.js; improves approval rates. Optional.

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

    # Top-level payer needs an email; names/phone are added only when real.
    payer: dict = {
        'email': payer_email or order.email or (order.user.email if order.user else ''),
    }
    if first:
        payer['first_name'] = first
    if last:
        payer['last_name'] = last
    phone = _payer_phone(order)
    if phone:
        payer['phone'] = {'area_code': '51', 'number': phone}

    payload: dict = {
        'transaction_amount': transaction_amount,
        'token': token,
        'description': f'Pedido {order.order_number} - Qolca Solutions'[:255],
        'installments': int(installments) if installments else 1,
        'payment_method_id': payment_method_id,
        'payer': payer,
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
    # Real additional_info (items / payer details / shipping) — improves
    # MP's antifraud scoring. Omitted entirely when there is nothing real.
    additional_info = _build_additional_info(order)
    if additional_info:
        payload['additional_info'] = additional_info
    notif_url = _notification_url()
    if notif_url:
        payload['notification_url'] = notif_url

    # Per-request idempotency key — guarantees retries do not create
    # duplicate payments on MP's side. device_id (X-meli-session-id) is
    # forwarded for antifraud when the browser supplied one.
    idem = str(uuid.uuid4())
    data = _mp_request(
        'POST', '/v1/payments', payload, idempotency_key=idem, device_id=device_id,
    )
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
