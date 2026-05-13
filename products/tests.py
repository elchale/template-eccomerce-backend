"""
Tests for the products app.
Coverage: ProductFilter.is_active filter.
"""
import pytest
from decimal import Decimal

from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

User = get_user_model()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def admin_user(db):
    return User.objects.create_user(
        username='admin@test.com',
        email='admin@test.com',
        password='testpass123',
        is_staff=True,
        is_superuser=True,
    )


@pytest.fixture
def admin_client(api_client, admin_user):
    api_client.force_authenticate(user=admin_user)
    return api_client


def _make_category():
    from products.models import Category
    cat, _ = Category.objects.get_or_create(
        slug='test-cat',
        defaults={'name': 'Test Category', 'is_active': True},
    )
    return cat


def _make_product(name='Product', slug='product', sku='SKU-001', is_active=True):
    from products.models import Product
    return Product.objects.create(
        name=name,
        slug=slug,
        base_price=Decimal('10.00'),
        sku=sku,
        is_active=is_active,
        category=_make_category(),
    )


# ---------------------------------------------------------------------------
# ProductFilter: is_active
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestProductFilterIsActive:
    list_url = '/api/admin/products/'

    def test_filter_active_true_returns_active(self, admin_client):
        _make_product(name='Active', slug='active-p', sku='SKU-ACT-1', is_active=True)
        _make_product(name='Inactive', slug='inactive-p', sku='SKU-INA-1', is_active=False)
        resp = admin_client.get(self.list_url + '?is_active=true')
        assert resp.status_code == 200
        results = resp.data['results']
        assert all(p['is_active'] for p in results)
        names = [p['name'] for p in results]
        assert 'Active' in names
        assert 'Inactive' not in names

    def test_filter_active_false_returns_inactive(self, admin_client):
        _make_product(name='Active2', slug='active-p2', sku='SKU-ACT-2', is_active=True)
        _make_product(name='Inactive2', slug='inactive-p2', sku='SKU-INA-2', is_active=False)
        resp = admin_client.get(self.list_url + '?is_active=false')
        assert resp.status_code == 200
        results = resp.data['results']
        assert all(not p['is_active'] for p in results)
        names = [p['name'] for p in results]
        assert 'Inactive2' in names
        assert 'Active2' not in names

    def test_no_filter_returns_all(self, admin_client):
        _make_product(name='ActiveAll', slug='active-all', sku='SKU-ALL-1', is_active=True)
        _make_product(name='InactiveAll', slug='inactive-all', sku='SKU-ALL-2', is_active=False)
        resp = admin_client.get(self.list_url)
        assert resp.status_code == 200
        names = [p['name'] for p in resp.data['results']]
        assert 'ActiveAll' in names
        assert 'InactiveAll' in names

    def test_non_admin_forbidden(self, api_client):
        resp = api_client.get(self.list_url + '?is_active=true')
        assert resp.status_code in (401, 403)
