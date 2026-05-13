"""Izipay/Lyra payment gateway service module.

This module handles all communication with the Izipay REST API
(https://api.micuentaweb.pe/api-payment/V4/).

Key points:
- Amounts are in centimos (smallest currency unit). S/ 1.00 = 100.
- HMAC-SHA-256 is used to verify IPN signatures — never trust client callbacks alone.
- `kr_answer_raw` must be the exact string Izipay sent; do NOT parse and
  re-serialize it as key order may differ and the hash would not match.
- BP1: strict sha256_hmac only — no fallback to 'password' key type.
"""
import hmac
import hashlib
import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class IzipayError(Exception):
    """Raised when the Izipay API returns an error or the request fails."""
    pass


def create_payment_token(order) -> str:
    """Call Izipay Charge/CreatePayment and return a formToken.

    The formToken is a short-lived JWT that the frontend uses to initialize
    the embedded payment form (via @lyracom/embedded-form-glue).

    Args:
        order: Order instance (must expose .total, .order_number, .user).

    Returns:
        formToken string.

    Raises:
        IzipayError: If the API call fails or returns an error status.
    """
    url = f'{settings.IZIPAY_API_URL}Charge/CreatePayment'

    # Izipay requires amount in centimos (integer)
    amount = int(order.total * 100)

    payload = {
        'amount': amount,
        'currency': 'PEN',
        'orderId': order.order_number,
        'formAction': 'PAYMENT',
        'customer': {
            'email': order.user.email,
            'billingDetails': {
                'firstName': order.user.first_name or order.user.email.split('@')[0],
                'lastName': order.user.last_name or '',
            },
        },
        'transactionOptions': {
            'cardOptions': {
                'paymentSource': 'EC',  # E-Commerce
            },
        },
        'contrib': 'Django/5.2.5_QolcaEccomerce',
    }

    try:
        response = requests.post(
            url,
            json=payload,
            auth=(settings.IZIPAY_SHOP_ID, settings.IZIPAY_API_KEY),
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as exc:
        logger.error('Izipay CreatePayment request failed: %s', exc)
        raise IzipayError(f'Error de conexión con Izipay: {exc}')

    if data.get('status') != 'SUCCESS':
        error_msg = data.get('answer', {}).get('errorMessage', 'Unknown error')
        logger.error(
            'Izipay CreatePayment error: status=%s message=%s',
            data.get('status'),
            error_msg,
        )
        raise IzipayError(f'Izipay rechazó la solicitud: {error_msg}')

    form_token = data['answer']['formToken']
    logger.info(
        'Izipay formToken created for order %s (amount=%d centimos)',
        order.order_number,
        amount,
    )
    return form_token


def verify_hash(kr_hash: str, kr_answer_raw: str, kr_hash_key: str = 'sha256_hmac') -> bool:
    """Verify an HMAC-SHA-256 signature from an Izipay IPN or client callback.

    BP1: Strict sha256_hmac only — only validates when kr_hash_key == 'sha256_hmac'.
    Any other key type returns False (rejected), never falls back.

    Args:
        kr_hash:       The ``kr-hash`` value received from Izipay.
        kr_answer_raw: The raw JSON string of ``kr-answer`` exactly as
                       received — do NOT parse and re-serialise.
        kr_hash_key:   Must be ``'sha256_hmac'`` or this returns False.

    Returns:
        ``True`` if the computed digest matches ``kr_hash``.
    """
    if kr_hash_key != 'sha256_hmac':
        logger.warning(
            'Izipay verify_hash: unsupported key type "%s" (only sha256_hmac allowed)',
            kr_hash_key,
        )
        return False

    key = settings.IZIPAY_HMAC_KEY

    computed = hmac.new(
        key.encode('utf-8'),
        kr_answer_raw.encode('utf-8'),
        hashlib.sha256,
    ).hexdigest()

    # compare_digest is constant-time — prevents timing attacks
    return hmac.compare_digest(computed, kr_hash)


def cancel_or_refund(transaction_uuid: str, amount_centimos: int) -> dict:
    """Cancel or refund a transaction via Izipay.

    If the transaction hasn't been captured yet, it cancels it (no money moved).
    If already captured, it creates a refund.

    IMPORTANT: payload MUST include 'amount' and 'currency' fields,
    or you'll get "input data validation error" (impresiones SKILL pitfall).

    Args:
        transaction_uuid: The Izipay transaction UUID from the IPN.
        amount_centimos: Amount to cancel/refund in centimos.

    Returns:
        The Izipay API response dict.

    Raises:
        IzipayError: If the API call fails or amount/currency are missing.
    """
    if not transaction_uuid:
        raise IzipayError('transaction_uuid is required for CancelOrRefund')
    if amount_centimos <= 0:
        raise IzipayError('amount_centimos must be positive for CancelOrRefund')

    url = f'{settings.IZIPAY_API_URL}Transaction/CancelOrRefund'

    payload: dict = {
        'uuid': transaction_uuid,
        'amount': amount_centimos,   # REQUIRED — omitting causes "input data validation error"
        'currency': 'PEN',           # REQUIRED — omitting causes "input data validation error"
    }

    try:
        response = requests.post(
            url,
            json=payload,
            auth=(settings.IZIPAY_SHOP_ID, settings.IZIPAY_API_KEY),
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as exc:
        logger.error('Izipay CancelOrRefund failed: %s', exc)
        raise IzipayError(f'Error al procesar reembolso: {exc}')

    if data.get('status') != 'SUCCESS':
        error_msg = data.get('answer', {}).get('errorMessage', 'Unknown error')
        logger.error('Izipay CancelOrRefund error: %s', error_msg)
        raise IzipayError(f'Izipay rechazó el reembolso: {error_msg}')

    logger.info('Izipay CancelOrRefund success for transaction %s', transaction_uuid)
    return data


def validate_credentials() -> bool:
    """Call Izipay Charge/SDKTest to verify credentials are valid.

    Useful as a health-check endpoint or during initial integration testing.

    Returns:
        ``True`` if the API responds with ``status == 'SUCCESS'``.
    """
    url = f'{settings.IZIPAY_API_URL}Charge/SDKTest'
    try:
        response = requests.post(
            url,
            json={'value': 'test'},
            auth=(settings.IZIPAY_SHOP_ID, settings.IZIPAY_API_KEY),
            timeout=10,
        )
        data = response.json()
        return data.get('status') == 'SUCCESS'
    except Exception as exc:
        logger.error('Izipay credential validation failed: %s', exc)
        return False
