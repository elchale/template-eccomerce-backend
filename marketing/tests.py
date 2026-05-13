"""
Tests for the marketing app.
Coverage: models, serializers, views (happy path, validation, permissions, 404).
"""
import io
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
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
def regular_user(db):
    return User.objects.create_user(
        username='user@test.com',
        email='user@test.com',
        password='testpass123',
    )


@pytest.fixture
def admin_client(api_client, admin_user):
    api_client.force_authenticate(user=admin_user)
    return api_client


@pytest.fixture
def user_client(api_client, regular_user):
    api_client.force_authenticate(user=regular_user)
    return api_client


def make_promocion(**kwargs):
    from marketing.models import Promocion
    now = timezone.now()
    defaults = dict(
        nombre='Test Promo',
        slug='test-promo',
        tipo=Promocion.Tipo.PORCENTAJE,
        valor_descuento=Decimal('10.00'),
        aplica_a_todo=True,
        fecha_inicio=now - timezone.timedelta(hours=1),
        fecha_fin=now + timezone.timedelta(days=7),
        es_activo=True,
        prioridad=0,
    )
    defaults.update(kwargs)
    return Promocion.objects.create(**defaults)


def make_banner(**kwargs):
    from marketing.models import Banner
    defaults = dict(
        nombre='Test Banner',
        tipo='hero',
        titulo='Big Sale',
        es_activo=True,
    )
    defaults.update(kwargs)
    return Banner.objects.create(**defaults)


def make_popup(**kwargs):
    from marketing.models import Popup
    defaults = dict(
        nombre='Test Popup',
        tipo='bienvenida',
        titulo='Welcome',
        mensaje='Hello there!',
        es_activo=True,
    )
    defaults.update(kwargs)
    return Popup.objects.create(**defaults)


def make_config(**kwargs):
    from marketing.models import ConfiguracionTienda
    defaults = dict(clave='test_key', valor='test_value')
    defaults.update(kwargs)
    return ConfiguracionTienda.objects.create(**defaults)


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestPromocionModel:
    def test_str(self):
        promo = make_promocion()
        assert str(promo) == 'Test Promo'

    def test_slug_unique(self):
        make_promocion()
        from django.db import IntegrityError
        with pytest.raises(IntegrityError):
            make_promocion(slug='test-promo', nombre='Another')


@pytest.mark.django_db
class TestBannerModel:
    def test_str(self):
        banner = make_banner()
        assert str(banner) == 'Test Banner'


@pytest.mark.django_db
class TestPopupModel:
    def test_str(self):
        popup = make_popup()
        assert str(popup) == 'Test Popup'


@pytest.mark.django_db
class TestConfiguracionTiendaModel:
    def test_str(self):
        config = make_config()
        assert str(config) == 'test_key'

    def test_clave_unique(self):
        make_config()
        from django.db import IntegrityError
        with pytest.raises(IntegrityError):
            make_config(clave='test_key', valor='other')


# ---------------------------------------------------------------------------
# Public view: Promociones
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestActivePromocionListView:
    url = '/api/marketing/promociones/'

    def test_happy_path_returns_active(self, api_client):
        make_promocion()
        resp = api_client.get(self.url)
        assert resp.status_code == 200
        assert len(resp.data['results']) == 1

    def test_inactive_excluded(self, api_client):
        make_promocion(es_activo=False)
        resp = api_client.get(self.url)
        assert resp.status_code == 200
        assert len(resp.data['results']) == 0

    def test_expired_excluded(self, api_client):
        make_promocion(
            fecha_fin=timezone.now() - timezone.timedelta(hours=1)
        )
        resp = api_client.get(self.url)
        assert resp.status_code == 200
        assert len(resp.data['results']) == 0

    def test_future_excluded(self, api_client):
        make_promocion(
            fecha_inicio=timezone.now() + timezone.timedelta(hours=1)
        )
        resp = api_client.get(self.url)
        assert resp.status_code == 200
        assert len(resp.data['results']) == 0

    def test_no_auth_required(self, api_client):
        resp = api_client.get(self.url)
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Public view: Banners
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestActiveBannerListView:
    url = '/api/marketing/banners/'

    def test_happy_path(self, api_client):
        make_banner()
        resp = api_client.get(self.url)
        assert resp.status_code == 200
        assert len(resp.data['results']) == 1

    def test_filter_by_tipo(self, api_client):
        make_banner(nombre='Hero Banner', tipo='hero')
        make_banner(nombre='Announce Banner', tipo='anuncio')
        resp = api_client.get(self.url + '?tipo=hero')
        assert resp.status_code == 200
        assert all(b['tipo'] == 'hero' for b in resp.data['results'])

    def test_inactive_excluded(self, api_client):
        make_banner(es_activo=False)
        resp = api_client.get(self.url)
        assert resp.status_code == 200
        assert len(resp.data['results']) == 0

    def test_no_auth_required(self, api_client):
        resp = api_client.get(self.url)
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Public view: Popups
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestActivePopupListView:
    url = '/api/marketing/popups/'

    def test_happy_path(self, api_client):
        make_popup()
        resp = api_client.get(self.url)
        assert resp.status_code == 200
        assert len(resp.data['results']) == 1

    def test_filter_by_tipo(self, api_client):
        make_popup()
        make_popup(nombre='Cart Popup', tipo='abandono_carrito')
        resp = api_client.get(self.url + '?tipo=bienvenida')
        assert resp.status_code == 200
        assert all(p['tipo'] == 'bienvenida' for p in resp.data['results'])

    def test_inactive_excluded(self, api_client):
        make_popup(es_activo=False)
        resp = api_client.get(self.url)
        assert resp.status_code == 200
        assert len(resp.data['results']) == 0

    def test_no_auth_required(self, api_client):
        resp = api_client.get(self.url)
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Public view: Configuracion
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestConfiguracionView:
    url = '/api/marketing/configuracion/'

    def test_returns_dict(self, api_client):
        make_config(clave='site_name', valor='My Store')
        resp = api_client.get(self.url)
        assert resp.status_code == 200
        assert resp.data.get('site_name') == 'My Store'

    def test_no_auth_required(self, api_client):
        resp = api_client.get(self.url)
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Public view: Search suggestions
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestSearchSuggestionsView:
    url = '/api/search/suggestions/'

    def _create_product(self, name='Test Product'):
        from products.models import Category, Product
        slug = name.lower().replace(' ', '-')
        cat, _ = Category.objects.get_or_create(
            slug='search-cat', defaults={'name': 'Category', 'is_active': True}
        )
        sku = f'SKU-{slug[:8].upper()}'
        return Product.objects.create(
            name=name,
            slug=slug,
            base_price=Decimal('10.00'),
            sku=sku,
            is_active=True,
            category=cat,
        )

    def test_returns_results(self, api_client):
        self._create_product('Red T-Shirt')
        resp = api_client.get(self.url + '?q=red')
        assert resp.status_code == 200
        assert len(resp.data) == 1
        assert resp.data[0]['name'] == 'Red T-Shirt'

    def test_min_2_chars(self, api_client):
        self._create_product('Alpha Product')
        resp = api_client.get(self.url + '?q=a')
        assert resp.status_code == 200
        assert resp.data == []

    def test_no_query_returns_empty(self, api_client):
        resp = api_client.get(self.url)
        assert resp.status_code == 200
        assert resp.data == []

    def test_max_5_results(self, api_client):
        for i in range(7):
            self._create_product(f'Widget {i}')
        resp = api_client.get(self.url + '?q=widget')
        assert resp.status_code == 200
        assert len(resp.data) <= 5

    def test_inactive_product_excluded(self, api_client):
        self._create_product('Inactive Widget')
        from products.models import Product
        Product.objects.filter(name='Inactive Widget').update(is_active=False)
        resp = api_client.get(self.url + '?q=inactive')
        assert resp.status_code == 200
        assert resp.data == []

    def test_no_auth_required(self, api_client):
        resp = api_client.get(self.url + '?q=anything')
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Admin views: Promociones CRUD
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestAdminPromocionViewSet:
    list_url = '/api/admin/marketing/promociones/'

    def _detail_url(self, pk):
        return f'/api/admin/marketing/promociones/{pk}/'

    def _valid_payload(self, **overrides):
        now = timezone.now()
        data = {
            'nombre': 'New Promo',
            'slug': 'new-promo',
            'tipo': 'porcentaje',
            'valor_descuento': '15.00',
            'aplica_a_todo': True,
            'fecha_inicio': (now - timezone.timedelta(hours=1)).isoformat(),
            'fecha_fin': (now + timezone.timedelta(days=7)).isoformat(),
            'es_activo': True,
            'prioridad': 0,
        }
        data.update(overrides)
        return data

    def test_list_requires_admin(self, user_client):
        resp = user_client.get(self.list_url)
        assert resp.status_code == 403

    def test_list_requires_auth(self, api_client):
        resp = api_client.get(self.list_url)
        assert resp.status_code in (401, 403)

    def test_admin_can_list(self, admin_client):
        make_promocion()
        resp = admin_client.get(self.list_url)
        assert resp.status_code == 200

    def test_admin_can_create(self, admin_client):
        resp = admin_client.post(self.list_url, self._valid_payload(), format='json')
        assert resp.status_code == 201
        assert resp.data['nombre'] == 'New Promo'

    def test_create_validation_fecha_fin_before_inicio(self, admin_client):
        now = timezone.now()
        payload = self._valid_payload(
            fecha_inicio=(now + timezone.timedelta(days=1)).isoformat(),
            fecha_fin=now.isoformat(),
        )
        resp = admin_client.post(self.list_url, payload, format='json')
        assert resp.status_code == 400
        assert 'fecha_fin' in resp.data

    def test_create_validation_porcentaje_over_100(self, admin_client):
        payload = self._valid_payload(
            tipo='porcentaje',
            valor_descuento='150.00',
        )
        resp = admin_client.post(self.list_url, payload, format='json')
        assert resp.status_code == 400

    def test_admin_can_retrieve(self, admin_client):
        promo = make_promocion()
        resp = admin_client.get(self._detail_url(promo.pk))
        assert resp.status_code == 200
        assert resp.data['id'] == promo.pk

    def test_retrieve_404(self, admin_client):
        resp = admin_client.get(self._detail_url(99999))
        assert resp.status_code == 404

    def test_admin_can_update(self, admin_client):
        promo = make_promocion()
        resp = admin_client.patch(
            self._detail_url(promo.pk),
            {'nombre': 'Updated Promo'},
            format='json',
        )
        assert resp.status_code == 200
        assert resp.data['nombre'] == 'Updated Promo'

    def test_admin_can_delete(self, admin_client):
        promo = make_promocion()
        resp = admin_client.delete(self._detail_url(promo.pk))
        assert resp.status_code == 204


# ---------------------------------------------------------------------------
# Admin views: Banners CRUD
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestAdminBannerViewSet:
    list_url = '/api/admin/marketing/banners/'

    def _detail_url(self, pk):
        return f'/api/admin/marketing/banners/{pk}/'

    def test_admin_can_create(self, admin_client):
        resp = admin_client.post(
            self.list_url,
            {'nombre': 'Hero', 'tipo': 'hero', 'es_activo': True},
            format='json',
        )
        assert resp.status_code == 201

    def test_non_admin_forbidden(self, user_client):
        resp = user_client.get(self.list_url)
        assert resp.status_code == 403

    def test_retrieve_404(self, admin_client):
        resp = admin_client.get(self._detail_url(99999))
        assert resp.status_code == 404

    def test_validation_fecha_fin_before_inicio(self, admin_client):
        now = timezone.now()
        resp = admin_client.post(
            self.list_url,
            {
                'nombre': 'Bad Banner',
                'tipo': 'hero',
                'es_activo': True,
                'fecha_inicio': (now + timezone.timedelta(days=1)).isoformat(),
                'fecha_fin': now.isoformat(),
            },
            format='json',
        )
        assert resp.status_code == 400
        assert 'fecha_fin' in resp.data


# ---------------------------------------------------------------------------
# Admin views: Popups CRUD
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestAdminPopupViewSet:
    list_url = '/api/admin/marketing/popups/'

    def _detail_url(self, pk):
        return f'/api/admin/marketing/popups/{pk}/'

    def test_admin_can_create(self, admin_client):
        resp = admin_client.post(
            self.list_url,
            {
                'nombre': 'Welcome Popup',
                'tipo': 'bienvenida',
                'titulo': 'Welcome!',
                'mensaje': 'Hello world',
                'es_activo': True,
            },
            format='json',
        )
        assert resp.status_code == 201

    def test_non_admin_forbidden(self, user_client):
        resp = user_client.get(self.list_url)
        assert resp.status_code == 403

    def test_retrieve_404(self, admin_client):
        resp = admin_client.get(self._detail_url(99999))
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Admin views: Configuracion
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestAdminConfiguracionView:
    url = '/api/admin/marketing/configuracion/'

    def test_admin_get_returns_flat_dict(self, admin_client):
        """GET must return a flat {clave: valor} dict, not a list of objects."""
        make_config(clave='foo', valor='bar')
        resp = admin_client.get(self.url)
        assert resp.status_code == 200
        # Response should be a dict keyed by clave
        assert isinstance(resp.data, dict)
        assert resp.data.get('foo') == 'bar'

    def test_admin_get_multiple_keys(self, admin_client):
        make_config(clave='alpha', valor='1')
        make_config(clave='beta', valor='2')
        resp = admin_client.get(self.url)
        assert resp.status_code == 200
        assert resp.data.get('alpha') == '1'
        assert resp.data.get('beta') == '2'

    def test_admin_patch_upserts(self, admin_client):
        resp = admin_client.patch(
            self.url, {'site_name': 'My Shop'}, format='json'
        )
        assert resp.status_code == 200
        from marketing.models import ConfiguracionTienda
        assert ConfiguracionTienda.objects.filter(clave='site_name', valor='My Shop').exists()

    def test_patch_preserves_get_contract(self, admin_client):
        """After PATCH, GET should still return the flat dict."""
        admin_client.patch(self.url, {'my_key': 'my_val'}, format='json')
        resp = admin_client.get(self.url)
        assert resp.status_code == 200
        assert isinstance(resp.data, dict)
        assert resp.data.get('my_key') == 'my_val'

    def test_patch_invalid_body(self, admin_client):
        resp = admin_client.patch(self.url, ['not', 'a', 'dict'], format='json')
        assert resp.status_code == 400

    def test_non_admin_forbidden(self, user_client):
        resp = user_client.get(self.url)
        assert resp.status_code == 403

    def test_unauthenticated_forbidden(self, api_client):
        resp = api_client.get(self.url)
        assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# Celery task
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestDeactivateExpiredPromocionesTask:
    def test_deactivates_expired(self):
        from marketing.tasks import deactivate_expired_promociones
        make_promocion(
            slug='expired-promo',
            fecha_fin=timezone.now() - timezone.timedelta(hours=1),
        )
        count = deactivate_expired_promociones()
        assert count == 1
        from marketing.models import Promocion
        assert not Promocion.objects.filter(slug='expired-promo', es_activo=True).exists()

    def test_skips_non_expired(self):
        from marketing.tasks import deactivate_expired_promociones
        make_promocion()
        count = deactivate_expired_promociones()
        assert count == 0


# ---------------------------------------------------------------------------
# N+1 regression: product promo pricing helpers
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestPrecioPromocionHelpers:
    def _make_product(self, price='100.00', slug='promo-product', sku='SKU-PROMO-1'):
        from products.models import Category, Product
        cat, _ = Category.objects.get_or_create(
            slug='cat-promo', defaults={'name': 'Cat', 'is_active': True}
        )
        return Product.objects.create(
            name='Promo Product',
            slug=slug,
            base_price=Decimal(price),
            sku=sku,
            is_active=True,
            category=cat,
        )

    def test_porcentaje_discount(self):
        from products.serializers.products import (
            _calculate_precio_promocion,
            _get_active_promo_for_product,
        )
        product = self._make_product()
        make_promocion(aplica_a_todo=True, tipo='porcentaje', valor_descuento=Decimal('10.00'))
        promo = _get_active_promo_for_product(product)
        assert promo is not None
        price = _calculate_precio_promocion(product, promo)
        assert price == Decimal('90.00')

    def test_monto_fijo_discount(self):
        from products.serializers.products import (
            _calculate_precio_promocion,
            _get_active_promo_for_product,
        )
        from marketing.models import Promocion
        product = self._make_product(price='50.00', slug='fixed-product', sku='SKU-FIXED-1')
        make_promocion(
            slug='fixed-promo',
            aplica_a_todo=True,
            tipo=Promocion.Tipo.MONTO_FIJO,
            valor_descuento=Decimal('15.00'),
        )
        promo = _get_active_promo_for_product(product)
        price = _calculate_precio_promocion(product, promo)
        assert price == Decimal('35.00')

    def test_no_promo_returns_none(self):
        from products.serializers.products import (
            _calculate_precio_promocion,
            _get_active_promo_for_product,
        )
        product = self._make_product(slug='no-promo-product', sku='SKU-NOPROMO')
        promo = _get_active_promo_for_product(product)
        assert promo is None
        assert _calculate_precio_promocion(product, None) is None

    def test_product_list_serializer_includes_promo_fields(self):
        from products.serializers.products import ProductListSerializer
        product = self._make_product(slug='list-promo-product', sku='SKU-LISTPROMO')
        make_promocion(slug='list-promo', aplica_a_todo=True)
        product.refresh_from_db()
        serializer = ProductListSerializer(product)
        data = serializer.data
        assert 'precio_promocion' in data
        assert 'promocion' in data
        assert data['precio_promocion'] == '90.00'
        assert data['promocion']['tipo'] == 'porcentaje'


# ---------------------------------------------------------------------------
# Image upload endpoints (banners + popups) — mocked GCS
# ---------------------------------------------------------------------------


def _make_fake_image(name='test.jpg', content_type='image/jpeg', size_bytes=1024):
    """Return a Django-compatible SimpleUploadedFile-like object."""
    from django.core.files.uploadedfile import SimpleUploadedFile
    content = b'\xff\xd8\xff' + b'\x00' * (size_bytes - 3)  # minimal JPEG header
    return SimpleUploadedFile(name, content, content_type=content_type)


@pytest.mark.django_db
class TestAdminBannerImageUpload:
    def _upload_url(self, pk):
        return f'/api/admin/marketing/banners/{pk}/upload-image/'

    def test_upload_desktop_image(self, admin_client):
        banner = make_banner()
        fake_url = 'https://storage.googleapis.com/bucket/marketing/banners/1/img.jpg'
        with patch('marketing.views.banners.upload_image', return_value=fake_url):
            resp = admin_client.post(
                self._upload_url(banner.pk),
                {'image': _make_fake_image()},
                format='multipart',
            )
        assert resp.status_code == 200
        assert resp.data['image_url'] == fake_url
        banner.refresh_from_db()
        assert banner.imagen_url == fake_url

    def test_upload_mobile_variant(self, admin_client):
        banner = make_banner()
        fake_url = 'https://storage.googleapis.com/bucket/marketing/banners/1/mobile.jpg'
        with patch('marketing.views.banners.upload_image', return_value=fake_url):
            resp = admin_client.post(
                self._upload_url(banner.pk) + '?variant=mobile',
                {'image': _make_fake_image()},
                format='multipart',
            )
        assert resp.status_code == 200
        banner.refresh_from_db()
        assert banner.imagen_movil_url == fake_url

    def test_upload_no_file_returns_400(self, admin_client):
        banner = make_banner()
        resp = admin_client.post(self._upload_url(banner.pk), {}, format='multipart')
        assert resp.status_code == 400
        assert 'detail' in resp.data

    def test_upload_non_admin_forbidden(self, user_client):
        banner = make_banner()
        resp = user_client.post(
            self._upload_url(banner.pk),
            {'image': _make_fake_image()},
            format='multipart',
        )
        assert resp.status_code == 403

    def test_upload_404_on_missing_banner(self, admin_client):
        resp = admin_client.post(
            self._upload_url(99999),
            {'image': _make_fake_image()},
            format='multipart',
        )
        assert resp.status_code == 404

    def test_upload_gcs_error_returns_400(self, admin_client):
        banner = make_banner()
        with patch('marketing.views.banners.upload_image', side_effect=Exception('GCS failure')):
            resp = admin_client.post(
                self._upload_url(banner.pk),
                {'image': _make_fake_image()},
                format='multipart',
            )
        assert resp.status_code == 400
        assert 'GCS failure' in resp.data['detail']


@pytest.mark.django_db
class TestAdminPopupImageUpload:
    def _upload_url(self, pk):
        return f'/api/admin/marketing/popups/{pk}/upload-image/'

    def test_upload_image(self, admin_client):
        popup = make_popup()
        fake_url = 'https://storage.googleapis.com/bucket/marketing/popups/1/img.jpg'
        with patch('marketing.views.popups.upload_image', return_value=fake_url):
            resp = admin_client.post(
                self._upload_url(popup.pk),
                {'image': _make_fake_image()},
                format='multipart',
            )
        assert resp.status_code == 200
        assert resp.data['image_url'] == fake_url
        popup.refresh_from_db()
        assert popup.imagen_url == fake_url

    def test_upload_no_file_returns_400(self, admin_client):
        popup = make_popup()
        resp = admin_client.post(self._upload_url(popup.pk), {}, format='multipart')
        assert resp.status_code == 400

    def test_upload_non_admin_forbidden(self, user_client):
        popup = make_popup()
        resp = user_client.post(
            self._upload_url(popup.pk),
            {'image': _make_fake_image()},
            format='multipart',
        )
        assert resp.status_code == 403

    def test_upload_404_on_missing_popup(self, admin_client):
        resp = admin_client.post(
            self._upload_url(99999),
            {'image': _make_fake_image()},
            format='multipart',
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Seed site config management command
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestSeedSiteConfigCommand:
    def test_seeds_canonical_keys(self):
        from django.core.management import call_command
        from marketing.models import ConfiguracionTienda
        call_command('seed_site_config', verbosity=0)
        assert ConfiguracionTienda.objects.filter(clave='site_name').exists()
        assert ConfiguracionTienda.objects.filter(clave='currency', valor='PEN').exists()
        assert ConfiguracionTienda.objects.filter(clave='social_facebook').exists()
        assert ConfiguracionTienda.objects.filter(clave='free_shipping_threshold').exists()

    def test_idempotent_does_not_duplicate(self):
        from django.core.management import call_command
        from marketing.models import ConfiguracionTienda
        call_command('seed_site_config', verbosity=0)
        call_command('seed_site_config', verbosity=0)
        count = ConfiguracionTienda.objects.filter(clave='site_name').count()
        assert count == 1

    def test_seeds_all_16_keys(self):
        from django.core.management import call_command
        from marketing.models import ConfiguracionTienda
        from marketing.management.commands.seed_site_config import SEED_DATA
        call_command('seed_site_config', verbosity=0)
        for entry in SEED_DATA:
            assert ConfiguracionTienda.objects.filter(clave=entry['clave']).exists(), \
                f"Key '{entry['clave']}' not seeded"
