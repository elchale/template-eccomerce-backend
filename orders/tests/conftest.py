"""Test fixtures for Izipay payment tests (ADR §11)."""
import hashlib
import hmac
import json
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model

User = get_user_model()

# Fixed HMAC test key used in all tests
TEST_HMAC_KEY = 'test_hmac_key_for_unit_tests_only'
TEST_SHOP_ID = 'TEST_SHOP_ID'
TEST_API_KEY = 'TEST_API_KEY'


@pytest.fixture(autouse=True)
def patch_izipay_settings(settings):
    """Override Izipay settings for all tests — prevents real API calls."""
    settings.IZIPAY_SHOP_ID = TEST_SHOP_ID
    settings.IZIPAY_API_KEY = TEST_API_KEY
    settings.IZIPAY_HMAC_KEY = TEST_HMAC_KEY
    settings.IZIPAY_MODE = 'TEST'
    settings.IZIPAY_API_URL = 'https://api.micuentaweb.pe/api-payment/V4/'
    settings.TRUST_PROXY = False
    # Allow the Django test client's default server name
    if 'testserver' not in settings.ALLOWED_HOSTS:
        settings.ALLOWED_HOSTS = list(settings.ALLOWED_HOSTS) + ['testserver']


@pytest.fixture
def paid_user(db):
    """A regular authenticated user."""
    return User.objects.create_user(
        username='testbuyer',
        email='buyer@test.com',
        password='testpass123',
        first_name='Test',
        last_name='Buyer',
    )


@pytest.fixture
def pending_order(db, paid_user):
    """A pending order owned by paid_user with a known total."""
    from orders.models import Order
    order = Order.objects.create(
        user=paid_user,
        status=Order.Status.PENDING,
        subtotal=Decimal('10.00'),
        discount_amount=Decimal('0.00'),
        total=Decimal('10.00'),
        shipping_address='Av. Test 123, Lima',
        email='buyer@test.com',
    )
    # Ensure order_number was generated
    assert order.order_number.startswith('QLCA-')
    return order


def make_kr_answer(order_number: str, order_status: str = 'PAID', amount_centimos: int = 1000,
                   tx_uuid: str = 'test-tx-uuid-123', method_type: str = 'CARD') -> dict:
    """Build a minimal kr-answer dict matching Izipay's IPN payload structure."""
    return {
        'orderStatus': order_status,
        'orderDetails': {
            'orderId': order_number,
            'orderTotalAmount': amount_centimos,
        },
        'transactions': [
            {
                'uuid': tx_uuid,
                'paymentMethodType': method_type,
            }
        ],
    }


def sign_kr_answer(kr_answer_raw: str, key: str = TEST_HMAC_KEY) -> str:
    """Compute the sha256_hmac signature for a kr-answer raw string."""
    return hmac.new(
        key.encode('utf-8'),
        kr_answer_raw.encode('utf-8'),
        hashlib.sha256,
    ).hexdigest()


def make_valid_ipn_payload(
    order_number: str,
    order_status: str = 'PAID',
    amount_centimos: int = 1000,
    tx_uuid: str = 'test-tx-uuid-123',
    method_type: str = 'CARD',
    hmac_key: str = TEST_HMAC_KEY,
) -> dict:
    """Build a complete valid IPN payload dict (for JSON requests)."""
    kr_answer = make_kr_answer(order_number, order_status, amount_centimos, tx_uuid, method_type)
    kr_answer_raw = json.dumps(kr_answer, separators=(',', ':'))
    kr_hash = sign_kr_answer(kr_answer_raw, hmac_key)
    return {
        'kr-hash': kr_hash,
        'kr-hash-key': 'sha256_hmac',
        'kr-answer': kr_answer_raw,
    }


@pytest.fixture
def valid_ipn_payload(pending_order):
    """A valid IPN payload for the pending_order fixture (amount=10.00 = 1000 centimos)."""
    return make_valid_ipn_payload(
        order_number=pending_order.order_number,
        order_status='PAID',
        amount_centimos=1000,  # matches order.total = 10.00
    )
