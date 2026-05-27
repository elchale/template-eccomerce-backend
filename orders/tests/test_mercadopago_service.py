"""Service tests for orders/mercadopago.py.

Covers webhook signature verification (happy path, bad signature, missing
header). The HTTP-talking functions (create_payment, read_payment,
create_refund) are exercised end-to-end via the webhook tests in
test_mp_webhook.py — there the requests.request calls are mocked so we do
not hit the live MP API.
"""
import hashlib
import hmac

import pytest

from orders.mercadopago import (
    _GENERIC_CODE,
    _GENERIC_MESSAGE,
    _STATUS_DETAIL_MAP,
    extract_three_ds,
    resolve_status_detail,
    verify_webhook_signature,
)


# Fixed test secret used in all signature tests.
TEST_WEBHOOK_SECRET = 'test_mp_webhook_secret_for_unit_tests_only'


def _sign_manifest(data_id: str, request_id: str, ts: str, secret: str) -> str:
    """Reproduce MP's signing algorithm so we can build valid x-signature headers."""
    manifest = f'id:{str(data_id).lower()};request-id:{request_id};ts:{ts};'
    return hmac.new(
        secret.encode('utf-8'),
        manifest.encode('utf-8'),
        hashlib.sha256,
    ).hexdigest()


# ---------------------------------------------------------------------------
# verify_webhook_signature — happy path
# ---------------------------------------------------------------------------
def test_verify_webhook_signature_valid():
    """verify_webhook_signature returns True for a correctly signed manifest."""
    data_id = '12345678'
    request_id = 'req-abc-123'
    ts = '1704908010'

    expected = _sign_manifest(data_id, request_id, ts, TEST_WEBHOOK_SECRET)
    header = f'ts={ts},v1={expected}'

    assert verify_webhook_signature(header, request_id, data_id, TEST_WEBHOOK_SECRET) is True


def test_verify_webhook_signature_valid_with_reordered_parts():
    """verify_webhook_signature returns True regardless of ts/v1 order."""
    data_id = '12345678'
    request_id = 'req-abc-123'
    ts = '1704908010'

    expected = _sign_manifest(data_id, request_id, ts, TEST_WEBHOOK_SECRET)
    # MP usually sends ts first but the spec does not promise an order.
    header = f'v1={expected},ts={ts}'

    assert verify_webhook_signature(header, request_id, data_id, TEST_WEBHOOK_SECRET) is True


# ---------------------------------------------------------------------------
# verify_webhook_signature — bad signature
# ---------------------------------------------------------------------------
def test_verify_webhook_signature_tampered():
    """verify_webhook_signature returns False when v1 is forged."""
    data_id = '12345678'
    request_id = 'req-abc-123'
    ts = '1704908010'

    # Sign with the wrong secret on purpose.
    bad = _sign_manifest(data_id, request_id, ts, 'a-different-secret')
    header = f'ts={ts},v1={bad}'

    assert verify_webhook_signature(header, request_id, data_id, TEST_WEBHOOK_SECRET) is False


def test_verify_webhook_signature_tampered_data_id():
    """verify_webhook_signature returns False when the data_id is tampered."""
    data_id = '12345678'
    request_id = 'req-abc-123'
    ts = '1704908010'

    expected = _sign_manifest(data_id, request_id, ts, TEST_WEBHOOK_SECRET)
    header = f'ts={ts},v1={expected}'

    # Caller claims a different id than what was signed → mismatch.
    assert verify_webhook_signature(header, request_id, '99999999', TEST_WEBHOOK_SECRET) is False


# ---------------------------------------------------------------------------
# verify_webhook_signature — missing / malformed header
# ---------------------------------------------------------------------------
def test_verify_webhook_signature_missing_header():
    """verify_webhook_signature returns False when x-signature is empty."""
    assert verify_webhook_signature('', 'req-abc', '12345678', TEST_WEBHOOK_SECRET) is False


def test_verify_webhook_signature_missing_data_id():
    """verify_webhook_signature returns False when data_id is empty."""
    header = 'ts=1704908010,v1=abc'
    assert verify_webhook_signature(header, 'req-abc', '', TEST_WEBHOOK_SECRET) is False


def test_verify_webhook_signature_missing_secret():
    """verify_webhook_signature returns False when the secret is empty."""
    header = 'ts=1704908010,v1=abc'
    assert verify_webhook_signature(header, 'req-abc', '12345678', '') is False


def test_verify_webhook_signature_malformed_header():
    """verify_webhook_signature returns False for malformed headers."""
    # Missing v1
    assert verify_webhook_signature(
        'ts=1704908010', 'req', '12345678', TEST_WEBHOOK_SECRET,
    ) is False
    # Missing ts
    assert verify_webhook_signature(
        'v1=deadbeef', 'req', '12345678', TEST_WEBHOOK_SECRET,
    ) is False
    # Garbage
    assert verify_webhook_signature(
        'not-a-real-header', 'req', '12345678', TEST_WEBHOOK_SECRET,
    ) is False


# ---------------------------------------------------------------------------
# resolve_status_detail — mapped codes, unknown fallback, fraud masking
# ---------------------------------------------------------------------------
@pytest.mark.parametrize('status_detail', list(_STATUS_DETAIL_MAP.keys()))
def test_resolve_status_detail_maps_known_codes(status_detail):
    """Every mapped code returns exactly its (message, code) tuple."""
    message, code = resolve_status_detail(status_detail)
    assert (message, code) == _STATUS_DETAIL_MAP[status_detail]
    assert message and code  # non-empty


def test_resolve_status_detail_unknown_falls_back_to_generic():
    """Unknown codes return the generic message + code, never the raw code."""
    message, code = resolve_status_detail('cc_rejected_some_brand_new_code')
    assert message == _GENERIC_MESSAGE
    assert code == _GENERIC_CODE
    assert 'cc_rejected_some_brand_new_code' not in message


def test_resolve_status_detail_none_falls_back_to_generic():
    """None / empty status_detail returns the generic message + code."""
    assert resolve_status_detail(None) == (_GENERIC_MESSAGE, _GENERIC_CODE)
    assert resolve_status_detail('') == (_GENERIC_MESSAGE, _GENERIC_CODE)


@pytest.mark.parametrize('fraud_code', ['cc_rejected_high_risk', 'cc_rejected_blacklist'])
def test_resolve_status_detail_masks_fraud_reasons(fraud_code):
    """Fraud rejections must not reveal the reason to the customer."""
    message, code = resolve_status_detail(fraud_code)
    lowered = message.lower()
    assert 'riesgo' not in lowered
    assert 'fraude' not in lowered
    assert 'blacklist' not in lowered
    assert 'lista negra' not in lowered
    # The raw MP code is never echoed.
    assert fraud_code not in message
    assert code == 'declined'


# ---------------------------------------------------------------------------
# 3DS status_detail codes (ADR A5) — masked, safe
# ---------------------------------------------------------------------------
def test_resolve_pending_challenge_is_safe_needs_action():
    """pending_challenge maps to a safe needs_action message — no raw code."""
    message, code = resolve_status_detail('pending_challenge')
    assert code == 'needs_action'
    assert 'pending_challenge' not in message
    assert 'verificación de seguridad' in message.lower()


def test_resolve_cc_rejected_3ds_challenge_is_masked_declined():
    """cc_rejected_3ds_challenge maps to a safe declined message — no raw code."""
    message, code = resolve_status_detail('cc_rejected_3ds_challenge')
    assert code == 'declined'
    assert 'cc_rejected_3ds_challenge' not in message
    # Safe, non-leaking wording.
    assert message
    assert '3ds' not in message.lower()


# ---------------------------------------------------------------------------
# extract_three_ds — pulls only the challenge fields, no leakage
# ---------------------------------------------------------------------------
def test_extract_three_ds_returns_url_and_creq():
    payment = {
        'id': 1,
        'status': 'pending',
        'status_detail': 'pending_challenge',
        'three_ds_info': {
            'external_resource_url': 'https://challenge.bank.example/3ds',
            'creq': 'eyJjcmVxIjoiYWJjIn0=',
        },
    }
    out = extract_three_ds(payment)
    assert out == {
        'external_resource_url': 'https://challenge.bank.example/3ds',
        'creq': 'eyJjcmVxIjoiYWJjIn0=',
    }


def test_extract_three_ds_missing_info_returns_empty():
    assert extract_three_ds({'id': 1, 'status': 'approved'}) == {}
    assert extract_three_ds({'three_ds_info': None}) == {}
    assert extract_three_ds({}) == {}


def test_extract_three_ds_omits_blank_fields():
    payment = {'three_ds_info': {'external_resource_url': 'https://x/3ds', 'creq': ''}}
    out = extract_three_ds(payment)
    assert out == {'external_resource_url': 'https://x/3ds'}
    assert 'creq' not in out


def test_verify_webhook_signature_normalises_alphanumeric_id():
    """Alphanumeric ids are lowercased before signing — verifier matches MP behaviour."""
    data_id = 'AbCdEf-Mixed-Case'
    request_id = 'req-1'
    ts = '1704908010'

    # MP would sign the lowercased form.
    expected = _sign_manifest(data_id.lower(), request_id, ts, TEST_WEBHOOK_SECRET)
    header = f'ts={ts},v1={expected}'

    assert verify_webhook_signature(header, request_id, data_id, TEST_WEBHOOK_SECRET) is True
