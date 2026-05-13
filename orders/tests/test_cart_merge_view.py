"""Tests for the cart-merge endpoint used by the frontend on login.

The endpoint ships the guest cart from `localStorage` into the user's
server-backed cart so items added before login are not lost when the cart UI
switches from `localItems` to the server query.
"""
import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from orders.models import Cart, CartItem
from products.models import Category, Product, ProductVariant, VariantOption, VariantType

User = get_user_model()


@pytest.fixture
def user(db):
    return User.objects.create_user(username='mergeview', email='mv@test.com', password='pass')


@pytest.fixture
def category(db):
    return Category.objects.create(name='Cat', slug='cat')


@pytest.fixture
def product(db, category):
    return Product.objects.create(
        name='P1', slug='p1', sku='SKU1', base_price='50.00',
        category=category, stock=10, is_active=True,
    )


@pytest.fixture
def product_with_variant(db, category):
    p = Product.objects.create(
        name='P2', slug='p2', sku='SKU2', base_price='30.00',
        category=category, stock=0, is_active=True,
    )
    vtype = VariantType.objects.create(name='Size')
    vopt = VariantOption.objects.create(variant_type=vtype, value='M')
    variant = ProductVariant.objects.create(
        product=p, sku='SKU2-M', price='35.00', stock=5, is_active=True,
    )
    variant.options.add(vopt)
    return p, variant


@pytest.fixture
def auth_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.mark.django_db
class TestMergeCartView:
    def test_merges_guest_items_into_empty_cart(self, auth_client, user, product):
        resp = auth_client.post(
            '/api/cart/merge/',
            {'items': [{'product_id': product.pk, 'variant_id': None, 'quantity': 2}]},
            format='json',
        )
        assert resp.status_code == 200
        cart = Cart.objects.get(user=user)
        assert cart.items.count() == 1
        assert cart.items.first().quantity == 2

    def test_sums_quantities_with_existing_row(self, auth_client, user, product):
        cart = Cart.objects.create(user=user)
        CartItem.objects.create(cart=cart, product=product, quantity=3)

        resp = auth_client.post(
            '/api/cart/merge/',
            {'items': [{'product_id': product.pk, 'variant_id': None, 'quantity': 4}]},
            format='json',
        )
        assert resp.status_code == 200
        assert CartItem.objects.get(cart=cart, product=product, variant=None).quantity == 7

    def test_clamps_to_available_stock(self, auth_client, user, product):
        resp = auth_client.post(
            '/api/cart/merge/',
            {'items': [{'product_id': product.pk, 'variant_id': None, 'quantity': 999}]},
            format='json',
        )
        assert resp.status_code == 200
        assert CartItem.objects.get(cart__user=user, product=product).quantity == product.stock

    def test_skips_unknown_product_silently(self, auth_client, user, product):
        resp = auth_client.post(
            '/api/cart/merge/',
            {
                'items': [
                    {'product_id': 999999, 'variant_id': None, 'quantity': 1},
                    {'product_id': product.pk, 'variant_id': None, 'quantity': 1},
                ],
            },
            format='json',
        )
        assert resp.status_code == 200
        items = CartItem.objects.filter(cart__user=user)
        assert items.count() == 1
        assert items.first().product == product

    def test_merges_variant_items(self, auth_client, user, product_with_variant):
        product, variant = product_with_variant
        resp = auth_client.post(
            '/api/cart/merge/',
            {'items': [{'product_id': product.pk, 'variant_id': variant.pk, 'quantity': 2}]},
            format='json',
        )
        assert resp.status_code == 200
        item = CartItem.objects.get(cart__user=user, product=product, variant=variant)
        assert item.quantity == 2

    def test_requires_authentication(self):
        client = APIClient()
        resp = client.post('/api/cart/merge/', {'items': []}, format='json')
        assert resp.status_code == 401

    def test_empty_items_list_is_noop(self, auth_client, user):
        resp = auth_client.post('/api/cart/merge/', {'items': []}, format='json')
        assert resp.status_code == 200
        # Cart row created by get_or_create but with no items
        cart = Cart.objects.get(user=user)
        assert cart.items.count() == 0
