"""Order-on-payment flow tests (POST /api/checkout/pay + webhook + session status).

The Order is created ONLY when the MP payment is confirmed. These tests drive
the CheckoutSession state machine through every branch:

- approved → creates exactly one order, deducts stock, clears the cart.
- pending_challenge → NO order; returns three_ds + session_uuid; session stays processing.
- webhook approved (incl. after challenge) → creates the order (idempotent w/ sync).
- duplicate webhook / sync+webhook → exactly one order.
- rejected → no order, cart intact, masked {detail, code}.
- stock-out at confirm → MP refund + session failed + no order (no oversell).
- coupon validated at init + re-validated + incremented at order creation.
- anti-double-charge: 2nd pay with a paid session returns the order, no new payment.
- GET session/<uuid>/status (owner-only).

The single MP HTTP call inside create_payment / read_payment / create_refund is
mocked at orders.mercadopago.requests.request.
"""
import hashlib
import hmac
import json
from decimal import Decimal
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from coupons.models import Coupon
from orders.models import (
    Cart,
    CartItem,
    CheckoutSession,
    IpnEvent,
    Order,
    Payment,
)
from products.models import Category, Product, ProductVariant

User = get_user_model()

WEBHOOK_SECRET = 'test_mp_webhook_secret_checkout_pay'


@pytest.fixture(autouse=True)
def _mp_settings(settings):
    settings.MERCADOPAGO_ACCESS_TOKEN = 'test-access-token'
    settings.MERCADOPAGO_API_URL = 'https://api.mercadopago.com'
    settings.MERCADOPAGO_WEBHOOK_SECRET = WEBHOOK_SECRET
    if 'testserver' not in settings.ALLOWED_HOSTS:
        settings.ALLOWED_HOSTS = list(settings.ALLOWED_HOSTS) + ['testserver']


@pytest.fixture
def buyer(db):
    return User.objects.create_user(
        username='cobuyer', email='cobuyer@test.com', password='pass12345',
        first_name='Co', last_name='Buyer',
    )


@pytest.fixture
def category(db):
    return Category.objects.create(name='Cat', slug='cat-cp')


@pytest.fixture
def product(db, category):
    return Product.objects.create(
        name='Widget', slug='widget-cp', sku='WID-CP', base_price=Decimal('50.00'),
        stock=5, category=category,
    )


@pytest.fixture
def cart_with_item(db, buyer, product):
    cart = Cart.objects.create(user=buyer)
    CartItem.objects.create(cart=cart, product=product, quantity=2)
    return cart


def _auth_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def _pay_body(**extra):
    body = {
        'shipping_address': 'Av. Test 123, Lima',
        'email': 'cobuyer@test.com',
        'token': 'tok_test_123',
        'payment_method_id': 'visa',
        'installments': 1,
    }
    body.update(extra)
    return body


def _mp_response(status, total, status_detail='accredited', payment_id=70100, three_ds=None):
    body = {
        'id': payment_id,
        'status': status,
        'status_detail': status_detail,
        'transaction_amount': float(total),
    }
    if three_ds:
        body['three_ds_info'] = three_ds
    return body


def _post_pay(client, mp_body, body=None):
    with patch('orders.mercadopago.requests.request') as mocked:
        mocked.return_value.status_code = 200
        mocked.return_value.json.return_value = mp_body
        return client.post(reverse('checkout-pay'), body or _pay_body(), format='json')


# Webhook helpers (signed) -----------------------------------------------------

def _sign(data_id, request_id, ts, secret=WEBHOOK_SECRET):
    manifest = f'id:{str(data_id).lower()};request-id:{request_id};ts:{ts};'
    return hmac.new(secret.encode(), manifest.encode(), hashlib.sha256).hexdigest()


def _signed_headers(data_id, request_id='req-cp-1', ts='1704908010'):
    return {
        'HTTP_X_SIGNATURE': f'ts={ts},v1={_sign(data_id, request_id, ts)}',
        'HTTP_X_REQUEST_ID': request_id,
    }


def _webhook_body(payment_id):
    return json.dumps({
        'type': 'payment', 'action': 'payment.created', 'data': {'id': payment_id},
    }).encode()


# ---------------------------------------------------------------------------
# approved → creates order once, deducts stock, clears cart
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_pay_approved_creates_order_deducts_stock_clears_cart(buyer, product, cart_with_item):
    client = _auth_client(buyer)
    resp = _post_pay(client, _mp_response('approved', Decimal('100.00')))

    assert resp.status_code == 201
    assert resp.data['paid'] is True
    order = Order.objects.get(pk=resp.data['id'])
    assert order.payment_status == 'paid'
    assert order.status == Order.Status.CONFIRMED
    assert order.total == Decimal('100.00')
    assert order.items.count() == 1
    assert order.items.first().price == Decimal('50.00')

    # Stock deducted (5 - 2 = 3).
    product.refresh_from_db()
    assert product.stock == 3

    # Cart cleared.
    assert CartItem.objects.filter(cart=cart_with_item).count() == 0

    # Exactly one paid Payment row + one paid session.
    assert Payment.objects.filter(order=order, status='verified').count() == 1
    session = CheckoutSession.objects.get(order=order)
    assert session.status == CheckoutSession.Status.PAID


# ---------------------------------------------------------------------------
# pending_challenge → NO order, returns three_ds + session_uuid
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_pay_pending_challenge_creates_no_order(buyer, product, cart_with_item):
    client = _auth_client(buyer)
    three_ds = {'external_resource_url': 'https://bank/3ds', 'creq': 'creq-blob'}
    resp = _post_pay(
        client,
        _mp_response('pending', Decimal('100.00'), 'pending_challenge', three_ds=three_ds),
    )

    assert resp.status_code == 200
    assert resp.data['status'] == 'pending_challenge'
    assert resp.data['three_ds'] == three_ds
    session_uuid = resp.data['session_uuid']

    # No order; session still processing.
    assert Order.objects.count() == 0
    session = CheckoutSession.objects.get(uuid=session_uuid)
    assert session.status == CheckoutSession.Status.PROCESSING
    assert session.mp_payment_id == '70100'
    # Cart intact.
    assert CartItem.objects.filter(cart=cart_with_item).count() == 1


# ---------------------------------------------------------------------------
# webhook approved (after challenge) → creates the order
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_webhook_approved_after_challenge_creates_order(buyer, product, cart_with_item):
    client = _auth_client(buyer)
    three_ds = {'external_resource_url': 'https://bank/3ds', 'creq': 'creq-blob'}
    payment_id = 70200
    resp = _post_pay(
        client,
        _mp_response('pending', Decimal('100.00'), 'pending_challenge',
                     payment_id=payment_id, three_ds=three_ds),
    )
    session_uuid = resp.data['session_uuid']
    assert Order.objects.count() == 0

    # Webhook delivers the resolved approved payment.
    wh = Client()
    approved = {
        'id': payment_id, 'status': 'approved', 'status_detail': 'accredited',
        'transaction_amount': 100.00,
        'metadata': {'session_uuid': session_uuid, 'project': 'qlca'},
    }
    with patch('orders.mercadopago.requests.request') as mocked:
        mocked.return_value.status_code = 200
        mocked.return_value.json.return_value = approved
        wh_resp = wh.post(
            reverse('mercadopago-webhook'), data=_webhook_body(payment_id),
            content_type='application/json', **_signed_headers(payment_id),
        )

    assert wh_resp.status_code == 200
    session = CheckoutSession.objects.get(uuid=session_uuid)
    assert session.status == CheckoutSession.Status.PAID
    assert session.order_id is not None
    assert Order.objects.count() == 1
    product.refresh_from_db()
    assert product.stock == 3
    assert IpnEvent.objects.filter(
        gateway='mercadopago', processed_outcome='paid',
    ).count() == 1


# ---------------------------------------------------------------------------
# sync approved + duplicate webhook → exactly one order
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_sync_plus_webhook_creates_exactly_one_order(buyer, product, cart_with_item):
    client = _auth_client(buyer)
    payment_id = 70300
    resp = _post_pay(
        client, _mp_response('approved', Decimal('100.00'), payment_id=payment_id),
    )
    assert resp.status_code == 201
    session_uuid = resp.data['session_uuid']
    assert Order.objects.count() == 1

    # Webhook delivers the same approved payment twice (replay).
    wh = Client()
    approved = {
        'id': payment_id, 'status': 'approved', 'status_detail': 'accredited',
        'transaction_amount': 100.00,
        'metadata': {'session_uuid': session_uuid, 'project': 'qlca'},
    }
    with patch('orders.mercadopago.requests.request') as mocked:
        mocked.return_value.status_code = 200
        mocked.return_value.json.return_value = approved
        wh.post(reverse('mercadopago-webhook'), data=_webhook_body(payment_id),
                content_type='application/json', **_signed_headers(payment_id))
        wh.post(reverse('mercadopago-webhook'), data=_webhook_body(payment_id),
                content_type='application/json', **_signed_headers(payment_id))

    # Still exactly one order + one paid Payment row.
    assert Order.objects.count() == 1
    order = Order.objects.first()
    assert Payment.objects.filter(order=order, status='verified').count() == 1
    # Both webhook deliveries logged as duplicate.
    assert IpnEvent.objects.filter(
        gateway='mercadopago', processed_outcome='duplicate',
    ).count() == 2
    product.refresh_from_db()
    assert product.stock == 3


# ---------------------------------------------------------------------------
# rejected → no order, cart intact, masked {detail, code}
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_pay_rejected_no_order_cart_intact(buyer, product, cart_with_item):
    client = _auth_client(buyer)
    resp = _post_pay(
        client, _mp_response('rejected', Decimal('100.00'), 'cc_rejected_high_risk'),
    )

    assert resp.status_code == 402
    assert set(resp.data.keys()) == {'detail', 'code'}
    assert 'cc_rejected_high_risk' not in str(resp.data)
    assert Order.objects.count() == 0
    # Cart intact, stock untouched.
    assert CartItem.objects.filter(cart=cart_with_item).count() == 1
    product.refresh_from_db()
    assert product.stock == 5
    session = CheckoutSession.objects.first()
    assert session.status == CheckoutSession.Status.FAILED


# ---------------------------------------------------------------------------
# stock-out at confirm → refund + session failed + no order
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_stock_out_at_confirm_refunds_and_fails(buyer, product):
    # Cart wants 2 but stock drops to 1 before confirm (race).
    cart = Cart.objects.create(user=buyer)
    CartItem.objects.create(cart=cart, product=product, quantity=2)

    client = _auth_client(buyer)

    # First MP call = create_payment (approved); the refund is a second POST.
    # We pre-deduct stock to 1 right before the order is created by patching
    # create_payment to drop stock as a side effect.
    original_total = Decimal('100.00')

    def _request_side_effect(method, url, **kwargs):
        resp = type('R', (), {})()
        resp.status_code = 200
        if url.endswith('/refunds'):
            resp.json = lambda: {'id': 'ref_1', 'status': 'approved'}
        else:
            # create_payment: simulate the stock vanishing just before confirm.
            Product.objects.filter(pk=product.pk).update(stock=1)
            resp.json = lambda: _mp_response('approved', original_total)
        return resp

    with patch('orders.mercadopago.requests.request', side_effect=_request_side_effect) as mocked:
        resp = client.post(reverse('checkout-pay'), _pay_body(), format='json')

    assert resp.status_code == 409
    assert resp.data['code'] == 'out_of_stock'
    # No order created, stock not driven negative.
    assert Order.objects.count() == 0
    product.refresh_from_db()
    assert product.stock == 1
    # Refund was attempted (the /refunds POST happened).
    assert any(call.args[1].endswith('/refunds') for call in mocked.call_args_list)
    session = CheckoutSession.objects.first()
    assert session.status == CheckoutSession.Status.FAILED


# ---------------------------------------------------------------------------
# coupon validated + revalidated + incremented; promo applied in snapshot
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_coupon_incremented_on_order_creation(buyer, product, cart_with_item):
    now = timezone.now()
    coupon = Coupon.objects.create(
        code='SAVE10',
        discount_type=Coupon.DiscountType.FIXED,
        discount_value=Decimal('10.00'),
        valid_from=now - timedelta(days=1),
        valid_until=now + timedelta(days=1),
        is_active=True,
        usage_limit=5,
        times_used=0,
    )
    client = _auth_client(buyer)
    # subtotal 100 - 10 coupon = 90.
    resp = _post_pay(
        client, _mp_response('approved', Decimal('90.00')),
        body=_pay_body(coupon_code='SAVE10'),
    )
    assert resp.status_code == 201
    order = Order.objects.get(pk=resp.data['id'])
    assert order.discount_amount == Decimal('10.00')
    assert order.total == Decimal('90.00')
    assert order.coupon_id == coupon.pk

    coupon.refresh_from_db()
    assert coupon.times_used == 1


@pytest.mark.django_db
def test_invalid_coupon_rejected_at_init(buyer, product, cart_with_item):
    client = _auth_client(buyer)
    resp = _post_pay(
        client, _mp_response('approved', Decimal('100.00')),
        body=_pay_body(coupon_code='NOPE'),
    )
    assert resp.status_code == 400
    assert 'detail' in resp.data
    assert Order.objects.count() == 0


@pytest.mark.django_db
def test_promo_applied_in_snapshot(buyer, category):
    from marketing.models import Promocion

    prod = Product.objects.create(
        name='Promo W', slug='promo-w-cp', sku='PW-CP',
        base_price=Decimal('100.00'), stock=10, category=category,
    )
    now = timezone.now()
    Promocion.objects.create(
        nombre='P', slug='p-cp', tipo=Promocion.Tipo.PORCENTAJE,
        valor_descuento=Decimal('10.00'), aplica_a_todo=True,
        fecha_inicio=now - timedelta(days=1), fecha_fin=now + timedelta(days=1),
        es_activo=True, prioridad=10,
    )
    cart = Cart.objects.create(user=buyer)
    CartItem.objects.create(cart=cart, product=prod, quantity=1)

    client = _auth_client(buyer)
    # 10% off 100 = 90.
    resp = _post_pay(client, _mp_response('approved', Decimal('90.00')))
    assert resp.status_code == 201
    order = Order.objects.get(pk=resp.data['id'])
    assert order.items.first().price == Decimal('90.00')
    assert order.total == Decimal('90.00')
    # Snapshot stored the discounted unit price.
    session = CheckoutSession.objects.get(order=order)
    assert session.items[0]['unit_price'] == '90.00'


# ---------------------------------------------------------------------------
# anti-double-charge: 2nd pay with a paid session returns the order, no charge
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_anti_double_charge_returns_existing_order(buyer, product, cart_with_item):
    client = _auth_client(buyer)
    resp1 = _post_pay(client, _mp_response('approved', Decimal('100.00')))
    assert resp1.status_code == 201
    order_id = resp1.data['id']

    # Second pay attempt: a paid session exists → return the order, no MP call.
    with patch('orders.mercadopago.requests.request') as mocked:
        resp2 = client.post(reverse('checkout-pay'), _pay_body(), format='json')

    assert resp2.status_code == 200
    assert resp2.data['paid'] is True
    assert resp2.data['id'] == order_id
    # No MP charge was made on the second attempt.
    assert mocked.called is False
    assert Order.objects.count() == 1


@pytest.mark.django_db
def test_anti_double_charge_in_flight_session_not_recharged(buyer, product, cart_with_item):
    client = _auth_client(buyer)
    # First pay → 3DS challenge leaves a processing session with a payment id.
    three_ds = {'external_resource_url': 'https://bank/3ds', 'creq': 'c'}
    resp1 = _post_pay(
        client,
        _mp_response('pending', Decimal('100.00'), 'pending_challenge', three_ds=three_ds),
    )
    session_uuid = resp1.data['session_uuid']

    # Second pay → in-flight session returned, no new MP charge.
    with patch('orders.mercadopago.requests.request') as mocked:
        resp2 = client.post(reverse('checkout-pay'), _pay_body(), format='json')

    assert resp2.status_code == 200
    assert resp2.data['status'] == 'processing'
    assert resp2.data['session_uuid'] == session_uuid
    assert mocked.called is False
    assert CheckoutSession.objects.count() == 1


# ---------------------------------------------------------------------------
# empty cart → 400
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_pay_empty_cart_rejected(buyer):
    Cart.objects.create(user=buyer)
    client = _auth_client(buyer)
    with patch('orders.mercadopago.requests.request') as mocked:
        resp = client.post(reverse('checkout-pay'), _pay_body(), format='json')
    assert resp.status_code == 400
    assert mocked.called is False


# ---------------------------------------------------------------------------
# session/status endpoint (owner-only)
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_session_status_returns_status_and_order_number(buyer, product, cart_with_item):
    client = _auth_client(buyer)
    resp = _post_pay(client, _mp_response('approved', Decimal('100.00')))
    session_uuid = resp.data['session_uuid']

    status_resp = client.get(
        reverse('checkout-session-status', kwargs={'session_uuid': session_uuid}),
    )
    assert status_resp.status_code == 200
    assert status_resp.data['status'] == 'paid'
    assert status_resp.data['order_number'].startswith('QLCA-')


@pytest.mark.django_db
def test_session_status_processing_has_no_order_number(buyer, product, cart_with_item):
    client = _auth_client(buyer)
    three_ds = {'external_resource_url': 'https://bank/3ds', 'creq': 'c'}
    resp = _post_pay(
        client,
        _mp_response('pending', Decimal('100.00'), 'pending_challenge', three_ds=three_ds),
    )
    session_uuid = resp.data['session_uuid']
    status_resp = client.get(
        reverse('checkout-session-status', kwargs={'session_uuid': session_uuid}),
    )
    assert status_resp.status_code == 200
    assert status_resp.data['status'] == 'processing'
    assert 'order_number' not in status_resp.data


@pytest.mark.django_db
def test_session_status_owner_only(buyer, product, cart_with_item):
    client = _auth_client(buyer)
    resp = _post_pay(client, _mp_response('approved', Decimal('100.00')))
    session_uuid = resp.data['session_uuid']

    other = User.objects.create_user(username='other', email='o@t.com', password='pass12345')
    other_client = _auth_client(other)
    status_resp = other_client.get(
        reverse('checkout-session-status', kwargs={'session_uuid': session_uuid}),
    )
    assert status_resp.status_code == 404
