"""View tests for the Mercado Pago process endpoint (/api/payments/mercadopago/process/).

Focus of this module (PART B of the error-hardening spec):
- A rejected payment surfaces ONLY a safe `{detail, code}` body — never MP's
  raw status_detail (e.g. cc_rejected_high_risk).
- A declined card (MercadoPagoError raised in _mp_request) also returns
  `{detail, code}` 402 with no raw MP text.
- An approved payment keeps its existing success shape.

The single MP HTTP call inside create_payment is mocked at
``orders.mercadopago.requests.request`` so we never hit the live API.
"""
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from orders.models import Order


@pytest.fixture(autouse=True)
def patch_mp_settings(settings):
    settings.MERCADOPAGO_ACCESS_TOKEN = 'test-access-token'
    settings.MERCADOPAGO_API_URL = 'https://api.mercadopago.com'
    if 'testserver' not in settings.ALLOWED_HOSTS:
        settings.ALLOWED_HOSTS = list(settings.ALLOWED_HOSTS) + ['testserver']


def _auth_client(user) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def _body(order) -> dict:
    return {
        'order_number': order.order_number,
        'token': 'tok_test_123',
        'payment_method_id': 'visa',
        'installments': 1,
        'payer': {'email': order.email},
    }


# ---------------------------------------------------------------------------
# Rejected payment (HTTP 200 from MP, status='rejected') → safe {detail, code}
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_process_rejected_returns_only_safe_detail_and_code(pending_order, paid_user):
    """A high_risk rejection must NOT echo the raw status_detail to the client."""
    client = _auth_client(paid_user)
    url = reverse('mercadopago-process')

    mp_payment = {
        'id': 555,
        'status': 'rejected',
        'status_detail': 'cc_rejected_high_risk',
        'transaction_amount': float(pending_order.total),
    }

    with patch('orders.mercadopago.requests.request') as mocked:
        mocked.return_value.status_code = 200
        mocked.return_value.json.return_value = mp_payment
        response = client.post(url, _body(pending_order), format='json')

    assert response.status_code == 402
    data = response.json()
    # Exactly the two safe keys — nothing else.
    assert set(data.keys()) == {'detail', 'code'}
    # The raw MP code is never exposed.
    assert 'cc_rejected_high_risk' not in str(data)
    assert data['code'] == 'declined'
    # Fraud reason masked.
    lowered = data['detail'].lower()
    assert 'riesgo' not in lowered and 'fraude' not in lowered
    # Order untouched.
    pending_order.refresh_from_db()
    assert pending_order.payment_status == 'unpaid'


@pytest.mark.django_db
def test_process_rejected_card_data_keeps_safe_code(pending_order, paid_user):
    """A fixable card-data rejection maps to its safe message + card_data_invalid."""
    client = _auth_client(paid_user)
    url = reverse('mercadopago-process')

    mp_payment = {
        'id': 556,
        'status': 'rejected',
        'status_detail': 'cc_rejected_bad_filled_security_code',
        'transaction_amount': float(pending_order.total),
    }

    with patch('orders.mercadopago.requests.request') as mocked:
        mocked.return_value.status_code = 200
        mocked.return_value.json.return_value = mp_payment
        response = client.post(url, _body(pending_order), format='json')

    assert response.status_code == 402
    data = response.json()
    assert set(data.keys()) == {'detail', 'code'}
    assert data['code'] == 'card_data_invalid'
    assert 'cc_rejected_bad_filled_security_code' not in str(data)


# ---------------------------------------------------------------------------
# Declined card (MP returns 4xx → MercadoPagoError) → safe {detail, code} 402
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_process_api_error_returns_safe_detail_and_code(pending_order, paid_user):
    """A 4xx from MP surfaces a safe message + code, never MP's raw body."""
    client = _auth_client(paid_user)
    url = reverse('mercadopago-process')

    mp_error_body = {
        'message': 'Invalid card token',
        'error': 'bad_request',
        'status_detail': 'cc_rejected_insufficient_amount',
        'cause': [{'description': 'super secret internal reason'}],
    }

    with patch('orders.mercadopago.requests.request') as mocked:
        mocked.return_value.status_code = 400
        mocked.return_value.json.return_value = mp_error_body
        response = client.post(url, _body(pending_order), format='json')

    assert response.status_code == 402
    data = response.json()
    assert set(data.keys()) == {'detail', 'code'}
    assert data['code'] == 'insufficient_funds'
    # None of MP's raw text leaks.
    assert 'Invalid card token' not in str(data)
    assert 'super secret internal reason' not in str(data)
    assert 'cc_rejected_insufficient_amount' not in str(data)


# ---------------------------------------------------------------------------
# Approved payment keeps the existing success shape (unchanged behaviour)
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_process_approved_marks_order_paid(pending_order, paid_user):
    client = _auth_client(paid_user)
    url = reverse('mercadopago-process')

    mp_payment = {
        'id': 777,
        'status': 'approved',
        'status_detail': 'accredited',
        'transaction_amount': float(pending_order.total),
    }

    with patch('orders.mercadopago.requests.request') as mocked:
        mocked.return_value.status_code = 200
        mocked.return_value.json.return_value = mp_payment
        response = client.post(url, _body(pending_order), format='json')

    assert response.status_code == 200
    data = response.json()
    assert data['paid'] is True
    assert data['status'] == 'approved'
    assert 'code' not in data  # success shape unchanged
    pending_order.refresh_from_db()
    assert pending_order.payment_status == 'paid'


# ---------------------------------------------------------------------------
# device_id is forwarded as X-meli-session-id; missing one must not break it
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# 3DS payload: create_payment carries three_d_secure_mode / capture / binary_mode
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_process_payload_carries_3ds_fields(pending_order, paid_user):
    """The /v1/payments payload must enable 3DS (optional) and binary_mode=False."""
    client = _auth_client(paid_user)
    url = reverse('mercadopago-process')

    mp_payment = {
        'id': 901,
        'status': 'approved',
        'status_detail': 'accredited',
        'transaction_amount': float(pending_order.total),
    }

    with patch('orders.mercadopago.requests.request') as mocked:
        mocked.return_value.status_code = 200
        mocked.return_value.json.return_value = mp_payment
        client.post(url, _body(pending_order), format='json')

    _args, kwargs = mocked.call_args
    payload = kwargs['json']
    assert payload['three_d_secure_mode'] == 'optional'
    assert payload['capture'] is True
    assert payload['binary_mode'] is False


# ---------------------------------------------------------------------------
# 3DS challenge: pending + pending_challenge → A3 shape, order NOT confirmed
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_process_pending_challenge_returns_a3_shape_and_does_not_confirm(pending_order, paid_user):
    """status=pending / status_detail=pending_challenge returns the challenge
    payload (A3 shape) and leaves the order unconfirmed/unpaid."""
    client = _auth_client(paid_user)
    url = reverse('mercadopago-process')

    mp_payment = {
        'id': 902,
        'status': 'pending',
        'status_detail': 'pending_challenge',
        'transaction_amount': float(pending_order.total),
        'three_ds_info': {
            'external_resource_url': 'https://challenge.bank.example/3ds',
            'creq': 'eyJjcmVxIjoiYWJjIn0=',
        },
    }

    with patch('orders.mercadopago.requests.request') as mocked:
        mocked.return_value.status_code = 200
        mocked.return_value.json.return_value = mp_payment
        response = client.post(url, _body(pending_order), format='json')

    assert response.status_code == 200
    data = response.json()
    # Exactly the A3 shape — no 'paid', no raw MP body.
    assert data['status'] == 'pending_challenge'
    assert data['payment_id'] == '902'
    assert data['three_ds'] == {
        'external_resource_url': 'https://challenge.bank.example/3ds',
        'creq': 'eyJjcmVxIjoiYWJjIn0=',
    }
    assert 'paid' not in data
    # CRITICAL: the order must NOT be confirmed or marked paid.
    pending_order.refresh_from_db()
    assert pending_order.payment_status == 'unpaid'
    assert pending_order.status == Order.Status.PENDING
    # No verified Payment row created.
    assert pending_order.payments.filter(status='verified').count() == 0
    # The payment id was stashed so the webhook can correlate.
    assert pending_order.mp_payment_id == '902'


@pytest.mark.django_db
def test_process_forwards_device_id_header(pending_order, paid_user):
    client = _auth_client(paid_user)
    url = reverse('mercadopago-process')

    mp_payment = {
        'id': 888,
        'status': 'approved',
        'status_detail': 'accredited',
        'transaction_amount': float(pending_order.total),
    }
    body = _body(pending_order)
    body['device_id'] = 'dev-session-abc-123'

    with patch('orders.mercadopago.requests.request') as mocked:
        mocked.return_value.status_code = 200
        mocked.return_value.json.return_value = mp_payment
        response = client.post(url, body, format='json')

    assert response.status_code == 200
    # The X-meli-session-id header was sent on the MP request.
    _args, kwargs = mocked.call_args
    assert kwargs['headers'].get('X-meli-session-id') == 'dev-session-abc-123'
