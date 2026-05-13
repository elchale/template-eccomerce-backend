"""Service tests for orders/izipay.py — ADR §11.2 (S1–S7)."""
import hashlib
import hmac
import json
from unittest.mock import MagicMock, patch

import pytest
from django.conf import settings

from orders.izipay import IzipayError, cancel_or_refund, create_payment_token, verify_hash
from orders.tests.conftest import TEST_HMAC_KEY, sign_kr_answer


# ---------------------------------------------------------------------------
# S1 — verify_hash valid
# ---------------------------------------------------------------------------
def test_verify_hash_valid():
    """S1: verify_hash returns True for a correctly signed payload."""
    payload = '{"orderStatus":"PAID"}'
    signature = sign_kr_answer(payload, TEST_HMAC_KEY)
    assert verify_hash(signature, payload, 'sha256_hmac') is True


# ---------------------------------------------------------------------------
# S2 — verify_hash tampered body
# ---------------------------------------------------------------------------
def test_verify_hash_tampered():
    """S2: verify_hash returns False when the payload has been tampered."""
    original = '{"orderStatus":"PAID"}'
    signature = sign_kr_answer(original, TEST_HMAC_KEY)
    tampered = '{"orderStatus":"UNPAID"}'
    assert verify_hash(signature, tampered, 'sha256_hmac') is False


# ---------------------------------------------------------------------------
# S3 — verify_hash wrong key type (BP1)
# ---------------------------------------------------------------------------
def test_verify_hash_wrong_key_type():
    """S3: verify_hash returns False when kr_hash_key is not 'sha256_hmac'."""
    payload = '{"orderStatus":"PAID"}'
    # Even with a valid signature, wrong key type must return False (BP1)
    signature = sign_kr_answer(payload, TEST_HMAC_KEY)
    assert verify_hash(signature, payload, 'password') is False
    assert verify_hash(signature, payload, 'hmac') is False
    assert verify_hash(signature, payload, '') is False


# ---------------------------------------------------------------------------
# S4 — create_payment_token happy path (mocked requests)
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_create_payment_token_success(pending_order):
    """S4: create_payment_token calls Izipay API and returns formToken."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        'status': 'SUCCESS',
        'answer': {
            'formToken': 'test-form-token-jwt-abc123',
        },
    }
    mock_response.raise_for_status = MagicMock()

    with patch('orders.izipay.requests.post', return_value=mock_response) as mock_post:
        token = create_payment_token(pending_order)

    assert token == 'test-form-token-jwt-abc123'
    mock_post.assert_called_once()
    call_kwargs = mock_post.call_args
    # Verify correct auth credentials
    assert call_kwargs[1]['auth'] == (settings.IZIPAY_SHOP_ID, settings.IZIPAY_API_KEY)
    # Verify amount is in centimos
    payload = call_kwargs[1]['json']
    assert payload['amount'] == 1000  # 10.00 * 100
    assert payload['currency'] == 'PEN'
    assert payload['orderId'] == pending_order.order_number


# ---------------------------------------------------------------------------
# S5 — create_payment_token non-SUCCESS raises IzipayError
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_create_payment_token_error(pending_order):
    """S5: create_payment_token raises IzipayError when Izipay returns non-SUCCESS."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        'status': 'ERROR',
        'answer': {
            'errorMessage': 'Invalid shop credentials',
        },
    }
    mock_response.raise_for_status = MagicMock()

    with patch('orders.izipay.requests.post', return_value=mock_response):
        with pytest.raises(IzipayError) as exc_info:
            create_payment_token(pending_order)

    assert 'Invalid shop credentials' in str(exc_info.value)


# ---------------------------------------------------------------------------
# S6 — cancel_or_refund happy path
# ---------------------------------------------------------------------------
def test_cancel_or_refund_success():
    """S6: cancel_or_refund returns the Izipay response dict on SUCCESS."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        'status': 'SUCCESS',
        'answer': {'transactionDetails': {}},
    }
    mock_response.raise_for_status = MagicMock()

    with patch('orders.izipay.requests.post', return_value=mock_response) as mock_post:
        result = cancel_or_refund('uuid-abc-123', 1000)

    assert result['status'] == 'SUCCESS'
    call_kwargs = mock_post.call_args
    payload = call_kwargs[1]['json']
    # Regression test: amount AND currency must be in payload (impresiones SKILL pitfall)
    assert payload['amount'] == 1000
    assert payload['currency'] == 'PEN'
    assert payload['uuid'] == 'uuid-abc-123'


# ---------------------------------------------------------------------------
# S7 — cancel_or_refund raises IzipayError when Izipay rejects
# ---------------------------------------------------------------------------
def test_cancel_or_refund_rejected():
    """S7: cancel_or_refund raises IzipayError for non-SUCCESS response."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        'status': 'ERROR',
        'answer': {'errorMessage': 'Transaction not found'},
    }
    mock_response.raise_for_status = MagicMock()

    with patch('orders.izipay.requests.post', return_value=mock_response):
        with pytest.raises(IzipayError) as exc_info:
            cancel_or_refund('bad-uuid', 1000)

    assert 'Transaction not found' in str(exc_info.value)


# ---------------------------------------------------------------------------
# S8 — cancel_or_refund requires amount and currency (regression)
# ---------------------------------------------------------------------------
def test_cancel_or_refund_validates_amount():
    """cancel_or_refund raises IzipayError for zero or negative amounts."""
    with pytest.raises(IzipayError):
        cancel_or_refund('uuid-123', 0)

    with pytest.raises(IzipayError):
        cancel_or_refund('uuid-123', -100)


# ---------------------------------------------------------------------------
# Order.save() generates QLCA order_number
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_order_save_generates_qlca_order_number(paid_user):
    """Order.save() generates QLCA-YYYYMMDD-XXXX format when order_number is blank."""
    from orders.models import Order
    from decimal import Decimal

    order = Order.objects.create(
        user=paid_user,
        status=Order.Status.PENDING,
        total=Decimal('5.00'),
        email='test@test.com',
    )
    assert order.order_number
    parts = order.order_number.split('-')
    assert len(parts) == 3
    assert parts[0] == 'QLCA'
    assert len(parts[1]) == 8  # YYYYMMDD
    assert len(parts[2]) == 4  # XXXX hex


@pytest.mark.django_db
def test_order_save_no_regeneration_on_update(paid_user):
    """Order.save() does NOT regenerate order_number on subsequent saves."""
    from orders.models import Order
    from decimal import Decimal

    order = Order.objects.create(
        user=paid_user,
        status=Order.Status.PENDING,
        total=Decimal('5.00'),
        email='test@test.com',
    )
    original_number = order.order_number
    order.notes = 'Updated notes'
    order.save(update_fields=['notes', 'updated'])

    order.refresh_from_db()
    assert order.order_number == original_number
