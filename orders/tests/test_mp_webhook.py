"""Integration tests for the Mercado Pago webhook (/pay).

Covers the invariants from the integration spec §8:
- Always returns HTTP 200 (invalid JSON, bad signature, errors).
- Writes an IpnEvent audit row per call.
- Authoritative re-fetch via GET /v1/payments/{id} — we never trust the
  webhook body alone.
- Self-filters by metadata.project=='qlca' so sibling-project (e.g. imp)
  events do not match our orders.
- Idempotent — replaying an approved event for an already-paid order writes
  an IpnEvent with outcome='duplicate' but does not double-create a Payment.
"""
import hashlib
import hmac
import json
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.test import Client
from django.urls import reverse

from orders.models import IpnEvent, Order, Payment


TEST_WEBHOOK_SECRET = 'test_mp_webhook_secret_for_webhook_tests'


@pytest.fixture(autouse=True)
def patch_mp_settings(settings):
    """Force the MP webhook secret on for every test in this module.

    Without a secret the view skips signature checks (so the server boots
    fine with empty MP env vars). Tests need the enforced path.
    """
    settings.MERCADOPAGO_WEBHOOK_SECRET = TEST_WEBHOOK_SECRET
    settings.MERCADOPAGO_ACCESS_TOKEN = 'test-access-token'
    settings.MERCADOPAGO_API_URL = 'https://api.mercadopago.com'


def _sign(data_id: str, request_id: str, ts: str, secret: str = TEST_WEBHOOK_SECRET) -> str:
    manifest = f'id:{str(data_id).lower()};request-id:{request_id};ts:{ts};'
    return hmac.new(secret.encode('utf-8'), manifest.encode('utf-8'), hashlib.sha256).hexdigest()


def _signed_headers(data_id: str, request_id: str = 'req-test-1', ts: str = '1704908010') -> dict:
    sig = _sign(data_id, request_id, ts)
    return {
        'HTTP_X_SIGNATURE': f'ts={ts},v1={sig}',
        'HTTP_X_REQUEST_ID': request_id,
    }


def _payment_payload(payment_id: str) -> bytes:
    return json.dumps({
        'type': 'payment',
        'action': 'payment.created',
        'data': {'id': payment_id},
    }).encode('utf-8')


# ---------------------------------------------------------------------------
# Invalid JSON → 200 + IpnEvent(bad_signature)
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_mp_webhook_invalid_json_returns_200():
    client = Client()
    url = reverse('mercadopago-webhook')

    response = client.post(url, data=b'not-json-at-all', content_type='application/json')

    assert response.status_code == 200
    # An IpnEvent should have been written for forensics.
    assert IpnEvent.objects.filter(gateway='mercadopago').exists()


# ---------------------------------------------------------------------------
# Bad signature → 200 + IpnEvent(bad_signature), no order touched
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_mp_webhook_bad_signature_returns_200(pending_order):
    client = Client()
    url = reverse('mercadopago-webhook')

    body = _payment_payload('12345678')
    # Forge the signature with the wrong secret.
    bad_sig = _sign('12345678', 'req-1', '1704908010', secret='wrong-secret')
    headers = {
        'HTTP_X_SIGNATURE': f'ts=1704908010,v1={bad_sig}',
        'HTTP_X_REQUEST_ID': 'req-1',
    }

    with patch('orders.mercadopago.requests.request') as mocked:
        response = client.post(url, data=body, content_type='application/json', **headers)

    # 200 even though the signature is wrong — MP would retry otherwise.
    assert response.status_code == 200
    # Critically, the GET /v1/payments/{id} re-fetch must NOT have happened.
    assert mocked.called is False
    # Order untouched.
    pending_order.refresh_from_db()
    assert pending_order.payment_status == 'unpaid'
    # Audit row written.
    assert IpnEvent.objects.filter(
        gateway='mercadopago', processed_outcome='bad_signature',
    ).exists()


# ---------------------------------------------------------------------------
# Happy path — payment.created/approved → order paid + IpnEvent(paid)
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_mp_webhook_payment_approved_marks_order_paid(pending_order):
    client = Client()
    url = reverse('mercadopago-webhook')

    payment_id = '99887766'
    body = _payment_payload(payment_id)
    headers = _signed_headers(payment_id)

    # MP responds to our authoritative re-fetch with an approved payment.
    mock_payment = {
        'id': int(payment_id),
        'status': 'approved',
        'status_detail': 'accredited',
        'transaction_amount': float(pending_order.total),
        'metadata': {
            'order_uuid': str(pending_order.uuid),
            'order_number': pending_order.order_number,
            'project': 'qlca',
        },
    }

    with patch('orders.mercadopago.requests.request') as mocked:
        mocked.return_value.status_code = 200
        mocked.return_value.json.return_value = mock_payment
        response = client.post(url, data=body, content_type='application/json', **headers)

    assert response.status_code == 200

    pending_order.refresh_from_db()
    assert pending_order.payment_status == 'paid'
    assert pending_order.mp_payment_id == payment_id
    assert pending_order.status == Order.Status.CONFIRMED  # auto-confirmed (eccomerce convention)

    assert Payment.objects.filter(
        order=pending_order, method='mercadopago', transaction_id=payment_id,
    ).count() == 1

    assert IpnEvent.objects.filter(
        gateway='mercadopago', order_number=pending_order.order_number,
        processed_outcome='paid',
    ).exists()


# ---------------------------------------------------------------------------
# Duplicate event → IpnEvent(duplicate), no second Payment row
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_mp_webhook_duplicate_event_is_no_op(pending_order):
    client = Client()
    url = reverse('mercadopago-webhook')

    payment_id = '11223344'
    body = _payment_payload(payment_id)
    headers = _signed_headers(payment_id)

    mock_payment = {
        'id': int(payment_id),
        'status': 'approved',
        'transaction_amount': float(pending_order.total),
        'metadata': {
            'order_uuid': str(pending_order.uuid),
            'order_number': pending_order.order_number,
            'project': 'qlca',
        },
    }

    with patch('orders.mercadopago.requests.request') as mocked:
        mocked.return_value.status_code = 200
        mocked.return_value.json.return_value = mock_payment

        # First delivery — order goes paid.
        client.post(url, data=body, content_type='application/json', **headers)
        # Second delivery — duplicate.
        client.post(url, data=body, content_type='application/json', **headers)

    pending_order.refresh_from_db()
    assert pending_order.payment_status == 'paid'
    # Only one Payment row even though MP delivered twice.
    assert Payment.objects.filter(order=pending_order, method='mercadopago').count() == 1
    # Both deliveries logged, the second as 'duplicate'.
    assert IpnEvent.objects.filter(
        gateway='mercadopago', processed_outcome='duplicate',
    ).count() == 1
    assert IpnEvent.objects.filter(
        gateway='mercadopago', processed_outcome='paid',
    ).count() == 1


# ---------------------------------------------------------------------------
# Sibling project (metadata.project='imp') → no_order + IpnEvent(no_order)
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_mp_webhook_sibling_project_is_ignored(pending_order):
    client = Client()
    url = reverse('mercadopago-webhook')

    payment_id = '55667788'
    body = _payment_payload(payment_id)
    headers = _signed_headers(payment_id)

    # Same MP account is shared with impresiones — its events arrive here too.
    # metadata.project='imp' must self-filter out and never touch our order.
    mock_payment = {
        'id': int(payment_id),
        'status': 'approved',
        'transaction_amount': float(pending_order.total),
        'metadata': {
            'order_uuid': str(pending_order.uuid),       # would otherwise match!
            'order_number': pending_order.order_number,  # would otherwise match!
            'project': 'imp',                             # but project filter rejects it
        },
    }

    with patch('orders.mercadopago.requests.request') as mocked:
        mocked.return_value.status_code = 200
        mocked.return_value.json.return_value = mock_payment
        response = client.post(url, data=body, content_type='application/json', **headers)

    assert response.status_code == 200

    pending_order.refresh_from_db()
    # Our order MUST NOT have been touched.
    assert pending_order.payment_status == 'unpaid'
    assert pending_order.mp_payment_id == ''
    assert Payment.objects.filter(order=pending_order).count() == 0

    assert IpnEvent.objects.filter(
        gateway='mercadopago', processed_outcome='no_order',
    ).exists()
