"""IPN handler tests for orders/views_payment.py — ADR §11.1 (cases 1–12).

All cases use the test HMAC key from conftest so no real Izipay API is called.
"""
import json
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.urls import reverse

from orders.models import Cart, CartItem, IpnEvent, Order, Payment
from orders.tests.conftest import (
    TEST_HMAC_KEY,
    make_valid_ipn_payload,
    sign_kr_answer,
)


IPN_URL = '/api/payments/izipay/ipn/'
CREATE_TOKEN_URL = '/api/payments/izipay/create-token/'
VERIFY_URL = '/api/payments/izipay/verify/'


# ===========================================================================
# Helper: post JSON IPN
# ===========================================================================
def post_ipn_json(client, payload: dict):
    return client.post(
        IPN_URL,
        data=json.dumps(payload),
        content_type='application/json',
    )


def post_ipn_form(client, payload: dict):
    """Post as form-encoded (kr-answer must be a JSON string in form body).

    Django's test client with explicit content_type does NOT URL-encode dicts —
    it calls force_bytes(data) which produces str(dict). We must pre-encode.
    """
    import urllib.parse
    encoded = urllib.parse.urlencode(payload)
    return client.post(
        IPN_URL,
        data=encoded,
        content_type='application/x-www-form-urlencoded',
    )


# ===========================================================================
# Case 1 — PAID happy path (JSON body)
# ===========================================================================
@pytest.mark.django_db
def test_ipn_paid_happy_path(client, pending_order, valid_ipn_payload):
    """Case 1: PAID IPN creates Payment, confirms order, logs IpnEvent('paid')."""
    with patch('orders.views_payment.send_payment_received_email') as mock_email, \
         patch('orders.views_payment.notify_admin_payment_received') as mock_admin, \
         patch('orders.views_payment.send_refund_email'):

        resp = post_ipn_json(client, valid_ipn_payload)

    assert resp.status_code == 200

    pending_order.refresh_from_db()
    assert pending_order.payment_status == 'paid'
    assert pending_order.status == Order.Status.CONFIRMED
    assert pending_order.payment_method == 'izipay'
    assert pending_order.izipay_transaction_id == 'test-tx-uuid-123'

    # Payment row created
    payment = Payment.objects.get(order=pending_order)
    assert payment.status == 'verified'
    assert payment.transaction_id == 'test-tx-uuid-123'

    # IpnEvent logged
    event = IpnEvent.objects.get(order_number=pending_order.order_number)
    assert event.processed_outcome == 'paid'

    # Tasks queued
    mock_email.delay.assert_called_once_with(pending_order.id)
    mock_admin.delay.assert_called_once_with(pending_order.id)


# ===========================================================================
# Case 2 — Duplicate PAID IPN (idempotent)
# ===========================================================================
@pytest.mark.django_db
def test_ipn_duplicate_paid(client, pending_order, valid_ipn_payload):
    """Case 2: Duplicate PAID IPN is idempotent — no second Payment row."""
    with patch('orders.views_payment.send_payment_received_email'), \
         patch('orders.views_payment.notify_admin_payment_received'), \
         patch('orders.views_payment.send_refund_email'):

        post_ipn_json(client, valid_ipn_payload)
        resp2 = post_ipn_json(client, valid_ipn_payload)

    assert resp2.status_code == 200

    # Only one Payment row
    assert Payment.objects.filter(order=pending_order).count() == 1

    # Second IpnEvent is 'duplicate'
    events = list(IpnEvent.objects.filter(order_number=pending_order.order_number).order_by('created'))
    assert len(events) == 2
    assert events[0].processed_outcome == 'paid'
    assert events[1].processed_outcome == 'duplicate'


# ===========================================================================
# Case 3 — REFUNDED IPN
# ===========================================================================
@pytest.mark.django_db
def test_ipn_refunded(client, pending_order, patch_izipay_settings):
    """Case 3: REFUNDED IPN transitions payment_status to refunded."""
    # First mark the order as paid so we can test refund
    pending_order.payment_status = 'paid'
    pending_order.save(update_fields=['payment_status', 'updated'])

    payload = make_valid_ipn_payload(
        order_number=pending_order.order_number,
        order_status='REFUNDED',
        amount_centimos=1000,
    )

    with patch('orders.views_payment.send_refund_email') as mock_refund:
        resp = post_ipn_json(client, payload)

    assert resp.status_code == 200

    pending_order.refresh_from_db()
    assert pending_order.payment_status == 'refunded'

    event = IpnEvent.objects.filter(order_number=pending_order.order_number).last()
    assert event.processed_outcome == 'refunded'
    mock_refund.delay.assert_called_once_with(pending_order.id)


# ===========================================================================
# Case 4 — CANCELLED IPN
# ===========================================================================
@pytest.mark.django_db
def test_ipn_cancelled(client, pending_order, patch_izipay_settings):
    """Case 4: CANCELLED IPN sets payment_status=refunded, logs 'cancelled'."""
    payload = make_valid_ipn_payload(
        order_number=pending_order.order_number,
        order_status='CANCELLED',
        amount_centimos=1000,
    )

    with patch('orders.views_payment.send_refund_email') as mock_refund:
        resp = post_ipn_json(client, payload)

    assert resp.status_code == 200

    pending_order.refresh_from_db()
    assert pending_order.payment_status == 'refunded'

    event = IpnEvent.objects.filter(order_number=pending_order.order_number).last()
    assert event.processed_outcome == 'cancelled'
    mock_refund.delay.assert_called_once_with(pending_order.id)


# ===========================================================================
# Case 5 — UNPAID (declined) — no-op
# ===========================================================================
@pytest.mark.django_db
def test_ipn_unpaid(client, pending_order, patch_izipay_settings):
    """Case 5: UNPAID IPN is a no-op — order stays pending/unpaid."""
    payload = make_valid_ipn_payload(
        order_number=pending_order.order_number,
        order_status='UNPAID',
        amount_centimos=1000,
    )

    resp = post_ipn_json(client, payload)
    assert resp.status_code == 200

    pending_order.refresh_from_db()
    assert pending_order.payment_status == 'unpaid'
    assert pending_order.status == Order.Status.PENDING

    event = IpnEvent.objects.filter(order_number=pending_order.order_number).last()
    assert event.processed_outcome == 'unpaid'


# ===========================================================================
# Case 6 — Missing / unknown order_number
# ===========================================================================
@pytest.mark.django_db
def test_ipn_missing_order(client, patch_izipay_settings):
    """Case 6: IPN with unknown order_number returns 200, logs 'no_order'."""
    payload = make_valid_ipn_payload(
        order_number='QLCA-99991231-ZZZZ',
        order_status='PAID',
        amount_centimos=1000,
    )

    resp = post_ipn_json(client, payload)
    assert resp.status_code == 200

    event = IpnEvent.objects.filter(order_number='QLCA-99991231-ZZZZ').last()
    assert event is not None
    assert event.processed_outcome == 'no_order'


# ===========================================================================
# Case 7 — Bad HMAC (tampered kr-hash)
# ===========================================================================
@pytest.mark.django_db
def test_ipn_bad_hmac(client, pending_order, valid_ipn_payload):
    """Case 7: Tampered kr-hash returns 400 and logs 'bad_signature'."""
    tampered = dict(valid_ipn_payload)
    tampered['kr-hash'] = 'deadbeef' * 8  # 64 hex chars, wrong value

    resp = post_ipn_json(client, tampered)
    assert resp.status_code == 400

    event = IpnEvent.objects.filter(order_number=pending_order.order_number).last()
    assert event is not None
    assert event.processed_outcome == 'bad_signature'

    # Order untouched
    pending_order.refresh_from_db()
    assert pending_order.payment_status == 'unpaid'


# ===========================================================================
# Case 8 — Wrong kr-hash-key ('password') — BP1
# ===========================================================================
@pytest.mark.django_db
def test_ipn_wrong_hash_key(client, pending_order, valid_ipn_payload):
    """Case 8: kr-hash-key='password' is rejected with 400, logs 'bad_signature', wrong_key."""
    payload = dict(valid_ipn_payload)
    payload['kr-hash-key'] = 'password'  # Not allowed (BP1)

    resp = post_ipn_json(client, payload)
    assert resp.status_code == 400

    event = IpnEvent.objects.filter(order_number=pending_order.order_number).last()
    assert event is not None
    assert event.processed_outcome == 'bad_signature'
    assert event.error_detail == 'wrong_key'


# ===========================================================================
# Case 9 — Amount mismatch (BP4)
# ===========================================================================
@pytest.mark.django_db
def test_ipn_amount_mismatch(client, pending_order, patch_izipay_settings):
    """Case 9: PAID IPN with wrong amount returns 200, leaves order unpaid, queues admin alert."""
    payload = make_valid_ipn_payload(
        order_number=pending_order.order_number,
        order_status='PAID',
        amount_centimos=999,  # expected is 1000 (10.00 * 100)
    )

    with patch('orders.views_payment.send_admin_amount_mismatch_alert') as mock_alert:
        resp = post_ipn_json(client, payload)

    assert resp.status_code == 200

    pending_order.refresh_from_db()
    assert pending_order.payment_status == 'unpaid'

    event = IpnEvent.objects.filter(order_number=pending_order.order_number).last()
    assert event.processed_outcome == 'bad_amount'
    assert 'expected=1000' in event.error_detail
    assert 'received=999' in event.error_detail

    mock_alert.delay.assert_called_once_with(pending_order.id, 1000, 999)


# ===========================================================================
# Case 10 — GET liveness probe
# ===========================================================================
def test_ipn_get_liveness(client):
    """Case 10: GET /api/payments/izipay/ipn/ returns 200 OK (liveness probe)."""
    resp = client.get(IPN_URL)
    assert resp.status_code == 200
    assert b'OK' in resp.content


# ===========================================================================
# Case 11 — JSON body (same as case 1, explicit content-type check)
# ===========================================================================
@pytest.mark.django_db
def test_ipn_json_body(client, pending_order, valid_ipn_payload):
    """Case 11: JSON body with application/json content-type is processed correctly."""
    with patch('orders.views_payment.send_payment_received_email'), \
         patch('orders.views_payment.notify_admin_payment_received'), \
         patch('orders.views_payment.send_refund_email'):

        resp = client.post(
            IPN_URL,
            data=json.dumps(valid_ipn_payload),
            content_type='application/json',
        )

    assert resp.status_code == 200
    pending_order.refresh_from_db()
    assert pending_order.payment_status == 'paid'


# ===========================================================================
# Case 12 — Form-encoded body
# ===========================================================================
@pytest.mark.django_db
def test_ipn_form_encoded_body(client, pending_order, patch_izipay_settings):
    """Case 12: Form-encoded body (kr-answer as JSON string) is processed correctly."""
    import json as json_mod
    from orders.tests.conftest import make_valid_ipn_payload as mvip

    # For form-encoded, kr-answer is a JSON string (URL-encoded by the test client)
    kr_answer_dict = {
        'orderStatus': 'PAID',
        'orderDetails': {
            'orderId': pending_order.order_number,
            'orderTotalAmount': 1000,
        },
        'transactions': [{'uuid': 'form-tx-uuid', 'paymentMethodType': 'CARD'}],
    }
    kr_answer_raw = json_mod.dumps(kr_answer_dict, separators=(',', ':'))
    kr_hash = sign_kr_answer(kr_answer_raw, TEST_HMAC_KEY)

    form_data = {
        'kr-hash': kr_hash,
        'kr-hash-key': 'sha256_hmac',
        'kr-answer': kr_answer_raw,
    }

    with patch('orders.views_payment.send_payment_received_email'), \
         patch('orders.views_payment.notify_admin_payment_received'), \
         patch('orders.views_payment.send_refund_email'):

        resp = post_ipn_form(client, form_data)

    assert resp.status_code == 200
    pending_order.refresh_from_db()
    assert pending_order.payment_status == 'paid'
    assert pending_order.izipay_transaction_id == 'form-tx-uuid'


# ===========================================================================
# BP2 — Raw-body re-verify (verify endpoint uses exact bytes)
# ===========================================================================
@pytest.mark.django_db
def test_verify_endpoint_raw_body(paid_user, pending_order, patch_izipay_settings):
    """BP2: /verify/ uses the exact raw string for HMAC, not re-serialized dict."""
    import json as json_mod
    from rest_framework.test import APIClient

    kr_answer_dict = {
        'orderStatus': 'PAID',
        'orderDetails': {'orderId': pending_order.order_number},
        'transactions': [{'uuid': 'v-tx', 'paymentMethodType': 'CARD'}],
    }
    # Compact with specific separators
    kr_answer_raw = json_mod.dumps(kr_answer_dict, separators=(',', ':'))
    kr_hash = sign_kr_answer(kr_answer_raw, TEST_HMAC_KEY)

    api_client = APIClient()
    api_client.force_authenticate(user=paid_user)
    resp = api_client.post(
        VERIFY_URL,
        data={
            'kr_hash': kr_hash,
            'kr_hash_key': 'sha256_hmac',
            'kr_answer_raw': kr_answer_raw,
        },
        format='json',
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data['paid'] is True
    assert data['order_number'] == pending_order.order_number


@pytest.mark.django_db
def test_verify_endpoint_no_raw_returns_no_raw(paid_user, pending_order, patch_izipay_settings):
    """BP2: If kr_answer_raw is missing, /verify/ returns {paid: false, reason: 'no_raw'}."""
    from rest_framework.test import APIClient

    api_client = APIClient()
    api_client.force_authenticate(user=paid_user)
    resp = api_client.post(
        VERIFY_URL,
        data={
            'kr_hash': 'some-hash',
            'kr_hash_key': 'sha256_hmac',
            # kr_answer_raw intentionally absent
        },
        format='json',
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data['paid'] is False
    assert data['reason'] == 'no_raw'


# ===========================================================================
# Yape payment method mapping (D3)
# ===========================================================================
@pytest.mark.django_db
def test_ipn_yape_payment_method(client, pending_order, patch_izipay_settings):
    """D3: E_WALLET paymentMethodType maps to payment_method='yape'."""
    from orders.tests.conftest import make_valid_ipn_payload as mvip

    payload = mvip(
        order_number=pending_order.order_number,
        order_status='PAID',
        amount_centimos=1000,
        method_type='E_WALLET',
    )

    with patch('orders.views_payment.send_payment_received_email'), \
         patch('orders.views_payment.notify_admin_payment_received'), \
         patch('orders.views_payment.send_refund_email'):

        resp = post_ipn_json(client, payload)

    assert resp.status_code == 200
    pending_order.refresh_from_db()
    assert pending_order.payment_method == 'yape'


# ===========================================================================
# Cart is cleared on PAID IPN (D5)
# ===========================================================================
@pytest.mark.django_db
def test_ipn_clears_cart_on_paid(client, pending_order, valid_ipn_payload, paid_user):
    """D5: Cart items are deleted when IPN PAID is received."""
    from products.models import Category, Product

    # Create a minimal product and cart item
    cat = Category.objects.create(name='Test Cat', slug='test-cat')
    product = Product.objects.create(
        name='Test Product', slug='test-prod',
        base_price=Decimal('10.00'), category=cat,
    )
    cart = Cart.objects.create(user=paid_user)
    CartItem.objects.create(cart=cart, product=product, quantity=1)

    assert CartItem.objects.filter(cart=cart).count() == 1

    with patch('orders.views_payment.send_payment_received_email'), \
         patch('orders.views_payment.notify_admin_payment_received'), \
         patch('orders.views_payment.send_refund_email'):

        post_ipn_json(client, valid_ipn_payload)

    assert CartItem.objects.filter(cart=cart).count() == 0


# ===========================================================================
# BP6 — Auto-confirm on PAID (confirmed status + OrderStatusHistory)
# ===========================================================================
@pytest.mark.django_db
def test_ipn_auto_confirms_order(client, pending_order, valid_ipn_payload):
    """BP6: Order auto-transitions to confirmed on PAID IPN."""
    with patch('orders.views_payment.send_payment_received_email'), \
         patch('orders.views_payment.notify_admin_payment_received'), \
         patch('orders.views_payment.send_refund_email'):

        post_ipn_json(client, valid_ipn_payload)

    pending_order.refresh_from_db()
    assert pending_order.status == Order.Status.CONFIRMED

    from orders.models import OrderStatusHistory
    history = OrderStatusHistory.objects.filter(
        order=pending_order, new_status='confirmed'
    ).last()
    assert history is not None
    assert 'Izipay' in history.note
