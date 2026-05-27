"""Tests that the active marketing Promocion discount flows through the cart,
checkout subtotal, OrderItem.price snapshot, and charged order.total.

Regression guard for the original bug: promos were display-only and customers
paid full price at checkout."""
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from coupons.models import Coupon
from marketing.models import Promocion
from orders.models import Cart, CartItem, Order
from orders.serializers.cart import CartSerializer
from products.models import (
    Category,
    Product,
    ProductVariant,
    VariantOption,
    VariantType,
)
from products.serializers.products import ProductDetailSerializer

User = get_user_model()


@pytest.fixture
def user(db):
    return User.objects.create_user(
        username='promo_user', email='promo@test.com', password='pass1234'
    )


@pytest.fixture
def category(db):
    return Category.objects.create(name='Promo Cat', slug='promo-cat')


@pytest.fixture
def product(db, category):
    return Product.objects.create(
        name='Promo Product',
        slug='promo-product',
        sku='PROMO-001',
        base_price=Decimal('100.00'),
        stock=50,
        category=category,
    )


def _make_promo(tipo, valor, **overrides):
    now = timezone.now()
    defaults = dict(
        nombre='Test Promo',
        slug=f'test-promo-{tipo}-{valor}-{timezone.now().timestamp()}',
        tipo=tipo,
        valor_descuento=Decimal(valor),
        aplica_a_todo=True,
        fecha_inicio=now - timedelta(days=1),
        fecha_fin=now + timedelta(days=1),
        es_activo=True,
        prioridad=10,
    )
    defaults.update(overrides)
    return Promocion.objects.create(**defaults)


def _auth_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def _serialize_cart(cart):
    cart = (
        Cart.objects.prefetch_related(
            'items__product__images',
            'items__variant__options__variant_type',
        ).get(pk=cart.pk)
    )
    return CartSerializer(cart).data


@pytest.mark.django_db
class TestCartPromoPricing:
    def test_active_percentage_promo_reduces_cart(self, user, product):
        _make_promo(Promocion.Tipo.PORCENTAJE, '10.00')
        cart = Cart.objects.create(user=user)
        CartItem.objects.create(cart=cart, product=product, quantity=2)

        data = _serialize_cart(cart)
        assert data['items'][0]['unit_price'] == '90.00'
        assert data['items'][0]['line_total'] == '180.00'
        assert data['subtotal'] == '180.00'

    def test_no_promo_is_full_price(self, user, product):
        cart = Cart.objects.create(user=user)
        CartItem.objects.create(cart=cart, product=product, quantity=2)

        data = _serialize_cart(cart)
        assert data['items'][0]['unit_price'] == '100.00'
        assert data['subtotal'] == '200.00'

    def test_variant_priced_item_gets_promo_on_variant_price(self, user, product):
        _make_promo(Promocion.Tipo.PORCENTAJE, '10.00')
        vt = VariantType.objects.create(name='Size')
        opt = VariantOption.objects.create(variant_type=vt, value='L')
        variant = ProductVariant.objects.create(
            product=product, sku='PROMO-001-L', price=Decimal('200.00'), stock=10
        )
        variant.options.add(opt)
        cart = Cart.objects.create(user=user)
        CartItem.objects.create(cart=cart, product=product, variant=variant, quantity=1)

        data = _serialize_cart(cart)
        # 10% off the VARIANT price (200), not the base (100).
        assert data['items'][0]['unit_price'] == '180.00'
        assert data['subtotal'] == '180.00'

    def test_monto_fijo_promo(self, user, product):
        _make_promo(Promocion.Tipo.MONTO_FIJO, '30.00')
        cart = Cart.objects.create(user=user)
        CartItem.objects.create(cart=cart, product=product, quantity=1)

        data = _serialize_cart(cart)
        assert data['items'][0]['unit_price'] == '70.00'

    def test_monto_fijo_clamped_at_zero(self, user, product):
        _make_promo(Promocion.Tipo.MONTO_FIJO, '500.00')
        cart = Cart.objects.create(user=user)
        CartItem.objects.create(cart=cart, product=product, quantity=1)

        data = _serialize_cart(cart)
        assert data['items'][0]['unit_price'] == '0.00'

    def test_future_promo_is_ignored(self, user, product):
        now = timezone.now()
        _make_promo(
            Promocion.Tipo.PORCENTAJE, '10.00',
            fecha_inicio=now + timedelta(days=1),
            fecha_fin=now + timedelta(days=2),
        )
        cart = Cart.objects.create(user=user)
        CartItem.objects.create(cart=cart, product=product, quantity=1)

        data = _serialize_cart(cart)
        assert data['items'][0]['unit_price'] == '100.00'

    def test_past_promo_is_ignored(self, user, product):
        now = timezone.now()
        _make_promo(
            Promocion.Tipo.PORCENTAJE, '10.00',
            fecha_inicio=now - timedelta(days=2),
            fecha_fin=now - timedelta(days=1),
        )
        cart = Cart.objects.create(user=user)
        CartItem.objects.create(cart=cart, product=product, quantity=1)

        data = _serialize_cart(cart)
        assert data['items'][0]['unit_price'] == '100.00'

    def test_inactive_promo_is_ignored(self, user, product):
        _make_promo(Promocion.Tipo.PORCENTAJE, '10.00', es_activo=False)
        cart = Cart.objects.create(user=user)
        CartItem.objects.create(cart=cart, product=product, quantity=1)

        data = _serialize_cart(cart)
        assert data['items'][0]['unit_price'] == '100.00'


@pytest.fixture
def _mp_settings(settings):
    settings.MERCADOPAGO_ACCESS_TOKEN = 'test-access-token'
    settings.MERCADOPAGO_API_URL = 'https://api.mercadopago.com'
    if 'testserver' not in settings.ALLOWED_HOSTS:
        settings.ALLOWED_HOSTS = list(settings.ALLOWED_HOSTS) + ['testserver']


@pytest.mark.django_db
@pytest.mark.usefixtures('_mp_settings')
class TestCheckoutPromoPricing:
    """Order-on-payment: promo/coupon pricing flows through the snapshot and
    the Order that is created when the MP payment is approved.

    The single MP HTTP call inside create_payment is mocked so the /pay
    endpoint sees an approved payment and creates the order from the session.
    """

    def _approved_mp(self, total):
        return {
            'id': 70001,
            'status': 'approved',
            'status_detail': 'accredited',
            'transaction_amount': float(total),
        }

    def _pay(self, user, expected_total=None, **extra):
        client = _auth_client(user)
        payload = {
            'shipping_address': 'Calle Falsa 123',
            'email': 'promo@test.com',
            'token': 'tok_test',
            'payment_method_id': 'visa',
            'installments': 1,
        }
        payload.update(extra)
        with patch('orders.mercadopago.requests.request') as mocked:
            mocked.return_value.status_code = 200
            mocked.return_value.json.return_value = self._approved_mp(
                expected_total if expected_total is not None else 0
            )
            return client.post(reverse('checkout-pay'), payload, format='json')

    def test_percentage_promo_applies_to_order(self, user, product):
        _make_promo(Promocion.Tipo.PORCENTAJE, '10.00')
        cart = Cart.objects.create(user=user)
        CartItem.objects.create(cart=cart, product=product, quantity=2)

        resp = self._pay(user, expected_total=Decimal('180.00'))
        assert resp.status_code == 201

        order = Order.objects.get(pk=resp.data['id'])
        assert order.subtotal == Decimal('180.00')
        assert order.discount_amount == Decimal('0.00')
        assert order.total == Decimal('180.00')
        item = order.items.first()
        assert item.price == Decimal('90.00')

    def test_no_promo_charges_full_price(self, user, product):
        cart = Cart.objects.create(user=user)
        CartItem.objects.create(cart=cart, product=product, quantity=2)

        resp = self._pay(user, expected_total=Decimal('200.00'))
        assert resp.status_code == 201
        order = Order.objects.get(pk=resp.data['id'])
        assert order.subtotal == Decimal('200.00')
        assert order.total == Decimal('200.00')
        assert order.items.first().price == Decimal('100.00')

    def test_variant_promo_on_order_item(self, user, product):
        _make_promo(Promocion.Tipo.PORCENTAJE, '10.00')
        variant = ProductVariant.objects.create(
            product=product, sku='PROMO-001-V', price=Decimal('200.00'), stock=10
        )
        cart = Cart.objects.create(user=user)
        CartItem.objects.create(cart=cart, product=product, variant=variant, quantity=1)

        resp = self._pay(user, expected_total=Decimal('180.00'))
        assert resp.status_code == 201
        order = Order.objects.get(pk=resp.data['id'])
        assert order.total == Decimal('180.00')
        assert order.items.first().price == Decimal('180.00')

    def test_monto_fijo_on_order(self, user, product):
        _make_promo(Promocion.Tipo.MONTO_FIJO, '30.00')
        cart = Cart.objects.create(user=user)
        CartItem.objects.create(cart=cart, product=product, quantity=1)

        resp = self._pay(user, expected_total=Decimal('70.00'))
        order = Order.objects.get(pk=resp.data['id'])
        assert order.items.first().price == Decimal('70.00')
        assert order.total == Decimal('70.00')

    def test_coupon_stacks_on_promo_discounted_subtotal(self, user, product):
        # 10% promo -> unit 90, subtotal 180. Then 50% coupon -> 90 off.
        _make_promo(Promocion.Tipo.PORCENTAJE, '10.00')
        now = timezone.now()
        Coupon.objects.create(
            code='HALF',
            discount_type=Coupon.DiscountType.PERCENTAGE,
            discount_value=Decimal('50.00'),
            valid_from=now - timedelta(days=1),
            valid_until=now + timedelta(days=1),
            is_active=True,
        )
        cart = Cart.objects.create(user=user)
        CartItem.objects.create(cart=cart, product=product, quantity=2)

        resp = self._pay(user, expected_total=Decimal('90.00'), coupon_code='HALF')
        assert resp.status_code == 201
        order = Order.objects.get(pk=resp.data['id'])
        assert order.subtotal == Decimal('180.00')
        assert order.discount_amount == Decimal('90.00')
        assert order.total == Decimal('90.00')

    def test_coupon_min_purchase_uses_discounted_subtotal(self, user, product):
        # Base subtotal would be 100; after 10% promo it's 90, below the 95 min.
        _make_promo(Promocion.Tipo.PORCENTAJE, '10.00')
        now = timezone.now()
        Coupon.objects.create(
            code='MIN95',
            discount_type=Coupon.DiscountType.FIXED,
            discount_value=Decimal('10.00'),
            min_purchase_amount=Decimal('95.00'),
            valid_from=now - timedelta(days=1),
            valid_until=now + timedelta(days=1),
            is_active=True,
        )
        cart = Cart.objects.create(user=user)
        CartItem.objects.create(cart=cart, product=product, quantity=1)

        resp = self._pay(user, coupon_code='MIN95')
        assert resp.status_code == 400
        assert 'detail' in resp.data

    def test_inactive_promo_charges_full_price(self, user, product):
        _make_promo(Promocion.Tipo.PORCENTAJE, '10.00', es_activo=False)
        cart = Cart.objects.create(user=user)
        CartItem.objects.create(cart=cart, product=product, quantity=1)

        resp = self._pay(user, expected_total=Decimal('100.00'))
        order = Order.objects.get(pk=resp.data['id'])
        assert order.total == Decimal('100.00')
        assert order.items.first().price == Decimal('100.00')


@pytest.mark.django_db
class TestProductDisplayUnchanged:
    def test_precio_promocion_still_base_based(self, product):
        _make_promo(Promocion.Tipo.PORCENTAJE, '10.00')
        data = ProductDetailSerializer(product).data
        # Product page discount is computed on base_price (100) -> 90.
        assert data['precio_promocion'] == '90.00'
        assert Decimal(data['base_price']) == Decimal('100.00')

    def test_precio_promocion_none_without_promo(self, product):
        data = ProductDetailSerializer(product).data
        assert data['precio_promocion'] is None
