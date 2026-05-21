"""Culqi payment gateway service module.

Culqi (https://culqi.com) is the active payment gateway, replacing Izipay.
This module wraps the Culqi REST API v2 (https://api.culqi.com/v2).

Key points:
- Amounts are in céntimos (smallest currency unit). S/ 1.00 = 100.
- Currency is always 'PEN' (Peruvian Soles).
- Auth is a Bearer token using the SECRET key — server-side only.
- Card data never reaches us: the browser tokenizes the card with Culqi
  Checkout Custom and sends only a short-lived token (tkn_…) to the backend.
- Two payment paths:
    * Card / Yape  → a `token` → create_charge() runs synchronously and is
      authoritative (the charge result is the source of truth).
    * PagoEfectivo / wallets / Cuotéalo → create_order() returns a Culqi
      Order; the customer pays later and Culqi notifies us via webhook.
"""
import logging
import time

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class CulqiError(Exception):
    """Raised when the Culqi API returns an error or the request fails.

    `user_message` carries a Spanish, customer-safe message (e.g. a declined
    card reason); `culqi_error` is the raw Culqi error object when available.
    """

    def __init__(self, message, culqi_error=None):
        super().__init__(message)
        self.user_message = message
        self.culqi_error = culqi_error or {}


def _culqi_request(method: str, path: str, payload: dict | None = None, timeout: int = 30) -> dict:
    """Perform an authenticated Culqi API request and return the parsed body.

    Culqi returns ``{"object": "error", ...}`` (with an HTTP 4xx) for declined
    cards, antifraud rejections and bad input. Those are surfaced as
    ``CulqiError`` carrying the user-facing message.
    """
    url = f'{settings.CULQI_API_URL}{path}'
    headers = {
        'Authorization': f'Bearer {settings.CULQI_SECRET_KEY}',
        'Content-Type': 'application/json',
    }

    try:
        response = requests.request(method, url, json=payload, headers=headers, timeout=timeout)
    except requests.RequestException as exc:
        logger.error('Culqi %s %s request failed: %s', method, path, exc)
        raise CulqiError(f'Error de conexión con Culqi: {exc}')

    try:
        data = response.json()
    except ValueError:
        logger.error('Culqi %s %s: non-JSON response (HTTP %s)', method, path, response.status_code)
        raise CulqiError('Culqi devolvió una respuesta inválida.')

    if isinstance(data, dict) and data.get('object') == 'error':
        user_message = (
            data.get('user_message')
            or data.get('merchant_message')
            or 'No se pudo procesar el pago.'
        )
        logger.warning(
            'Culqi %s %s error: code=%s merchant_message=%s',
            method, path, data.get('code'), data.get('merchant_message'),
        )
        raise CulqiError(user_message, culqi_error=data)

    if response.status_code >= 400:
        logger.error('Culqi %s %s HTTP %s: %s', method, path, response.status_code, data)
        raise CulqiError('Culqi rechazó la solicitud.')

    return data


def _order_phone(order) -> str:
    """Best-effort phone number for Culqi `client_details` (a required field).

    Culqi tolerates a placeholder for online orders; we use the order's
    contact phone when one is available.
    """
    return (getattr(order, 'phone', '') or '').strip() or '999999999'


def _customer_names(order) -> tuple[str, str]:
    """Best-effort first/last name for Culqi antifraud / client details.

    The Order model stores no name fields, so fall back to the associated
    User; if there is none, derive a placeholder from the order email.
    """
    user = getattr(order, 'user', None)
    email = order.email or (user.email if user else '') or 'cliente'
    first = ((user.first_name if user else '') or email.split('@')[0])[:50]
    last = ((user.last_name if user else '') or 'N/A')[:50]
    return first, last


def create_charge(order, token_id: str) -> dict:
    """Charge a Culqi card/Yape token for an order (synchronous, authoritative).

    The token comes from Culqi Checkout Custom in the browser and is already
    3DS-authenticated. ``capture=True`` charges and captures in one step.

    Args:
        order:    Order instance (must expose .total, .order_number, .uuid, .email).
        token_id: Culqi token id (tkn_…) produced by the browser checkout.

    Returns:
        The Culqi charge object (dict).

    Raises:
        CulqiError: If the card is declined or the API call fails. The message
                    is customer-safe and can be returned to the frontend.
    """
    first, last = _customer_names(order)
    payload = {
        'amount': int(order.total * 100),
        'currency_code': 'PEN',
        'email': order.email or (order.user.email if order.user else ''),
        'source_id': token_id,
        'capture': True,
        'description': f'Pedido {order.order_number} - Qolca Solutions'[:80],
        'antifraud_details': {
            'first_name': first,
            'last_name': last,
        },
        'metadata': {
            'order_number': order.order_number,
            'order_uuid': str(order.uuid),
            'project': 'qlca',
        },
    }
    data = _culqi_request('POST', '/charges', payload)
    logger.info(
        'Culqi charge %s created for order %s (amount=%d céntimos)',
        data.get('id'), order.order_number, payload['amount'],
    )
    return data


def create_order(order) -> dict:
    """Create a Culqi Order so the customer can pay with alternative methods.

    Alternative methods are PagoEfectivo, mobile wallets, bank apps and
    Cuotéalo — they cannot be charged synchronously. The customer pays later
    and the result arrives via the ``order.status.changed`` webhook.

    Card / Yape do NOT need an Order; use create_charge() for those.

    Returns:
        The Culqi order object (dict); its ``id`` is an ``ord_…`` string.

    Raises:
        CulqiError: If the API call fails.
    """
    first, last = _customer_names(order)
    payload = {
        'amount': int(order.total * 100),
        'currency_code': 'PEN',
        'description': f'Pedido {order.order_number}'[:80],
        'order_number': order.order_number,
        'client_details': {
            'first_name': first,
            'last_name': last,
            'email': order.email or (order.user.email if order.user else ''),
            'phone_number': _order_phone(order),
        },
        # Culqi requires a future expiration; give the customer 24h to pay.
        'expiration_date': int(time.time()) + 24 * 3600,
        'confirm': False,
        'metadata': {
            'order_number': order.order_number,
            'order_uuid': str(order.uuid),
            'project': 'qlca',
        },
    }
    data = _culqi_request('POST', '/orders', payload)
    logger.info('Culqi order %s created for order %s', data.get('id'), order.order_number)
    return data


def read_charge(charge_id: str) -> dict:
    """Re-fetch a charge from Culqi (used to authenticate webhook events)."""
    return _culqi_request('GET', f'/charges/{charge_id}')


def read_order(culqi_order_id: str) -> dict:
    """Re-fetch an order from Culqi (used to authenticate webhook events)."""
    return _culqi_request('GET', f'/orders/{culqi_order_id}')


def create_refund(charge_id: str, amount_centimos: int, reason: str = 'solicitud_comprador') -> dict:
    """Refund a Culqi charge, fully or partially.

    Args:
        charge_id:       The Culqi charge id (chr_…) to refund.
        amount_centimos: Amount to refund in céntimos.
        reason:          One of 'solicitud_comprador', 'duplicado', 'fraudulento'.

    Returns:
        The Culqi refund object (dict).

    Raises:
        CulqiError: If the API call fails.
    """
    payload = {
        'amount': int(amount_centimos),
        'charge_id': charge_id,
        'reason': reason,
    }
    data = _culqi_request('POST', '/refunds', payload)
    logger.info('Culqi refund created for charge %s (amount=%d)', charge_id, payload['amount'])
    return data
