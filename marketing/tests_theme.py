"""
Tests for the SiteTheme singleton, serializer, and API endpoints.
"""
import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient

from marketing.cache_keys import SITE_THEME_CACHE_KEY
from marketing.models import SiteTheme

User = get_user_model()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_singleton(db):
    """Ensure pk=1 singleton exists and is in a clean default state before each test."""
    SiteTheme.objects.filter(pk=1).delete()
    SiteTheme.objects.create(pk=1, theme_id='classic', custom_colors={})


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def staff_user(db):
    user = User.objects.create_user(
        username='staffuser',
        email='staff@test.com',
        password='testpass123',
        is_staff=True,
    )
    return user


@pytest.fixture
def regular_user(db):
    user = User.objects.create_user(
        username='regularuser',
        email='regular@test.com',
        password='testpass123',
        is_staff=False,
    )
    return user


@pytest.fixture
def staff_client(client, staff_user):
    client.force_authenticate(user=staff_user)
    return client


@pytest.fixture
def regular_client(client, regular_user):
    client.force_authenticate(user=regular_user)
    return client


# ---------------------------------------------------------------------------
# Public endpoint tests
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_public_theme_returns_defaults(client):
    """GET /api/marketing/theme/ returns 200 with the default classic theme."""
    url = reverse('public-theme')
    response = client.get(url)
    assert response.status_code == 200
    assert response.data['theme_id'] == 'classic'
    assert response.data['custom_colors'] == {}


@pytest.mark.django_db
def test_public_theme_auto_creates_singleton(client):
    """If pk=1 does not exist, GET public endpoint auto-creates it and returns 200."""
    SiteTheme.objects.filter(pk=1).delete()
    url = reverse('public-theme')
    response = client.get(url)
    assert response.status_code == 200
    assert response.data['theme_id'] == 'classic'
    assert SiteTheme.objects.filter(pk=1).exists()


@pytest.mark.django_db
def test_public_theme_cached(client):
    """Public endpoint returns cached value instead of DB value when cache is warm."""
    from django.core.cache import cache
    # Seed cache with a value that differs from the DB state
    cached_payload = {'theme_id': 'elegant', 'custom_colors': {'--color-primary': '#D4AF37'}}
    cache.set(SITE_THEME_CACHE_KEY, cached_payload, 60)

    url = reverse('public-theme')
    response = client.get(url)
    assert response.status_code == 200
    # Response must match cached payload, not the DB default (classic)
    assert response.data['theme_id'] == 'elegant'
    assert response.data['custom_colors'] == {'--color-primary': '#D4AF37'}

    cache.delete(SITE_THEME_CACHE_KEY)


# ---------------------------------------------------------------------------
# Admin endpoint — auth / permission tests
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_admin_theme_get_requires_staff(regular_client):
    """Non-staff user gets 403 on admin GET."""
    url = reverse('admin-theme')
    response = regular_client.get(url)
    assert response.status_code == 403


@pytest.mark.django_db
def test_admin_theme_get_unauthenticated(client):
    """Unauthenticated request to admin endpoint returns 401."""
    url = reverse('admin-theme')
    response = client.get(url)
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Admin GET
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_admin_theme_get_returns_catalog(staff_client):
    """Staff GET returns 200 with available_theme_ids list of 8 items."""
    url = reverse('admin-theme')
    response = staff_client.get(url)
    assert response.status_code == 200
    assert 'available_theme_ids' in response.data
    assert len(response.data['available_theme_ids']) == 8
    assert 'customizable_color_keys' in response.data
    assert len(response.data['customizable_color_keys']) == 14
    assert 'updated' in response.data
    assert response.data['theme_id'] == 'classic'


# ---------------------------------------------------------------------------
# Admin PUT / PATCH
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_admin_theme_put_valid(staff_client):
    """Staff PUT with valid theme_id updates the singleton and returns 200."""
    url = reverse('admin-theme')
    response = staff_client.put(url, {'theme_id': 'elegant'}, format='json')
    assert response.status_code == 200
    assert response.data['theme_id'] == 'elegant'
    assert SiteTheme.objects.get(pk=1).theme_id == 'elegant'


@pytest.mark.django_db
def test_admin_theme_patch_valid(staff_client):
    """Staff PATCH (partial) with valid theme_id updates the singleton."""
    url = reverse('admin-theme')
    response = staff_client.patch(url, {'theme_id': 'dark'}, format='json')
    assert response.status_code == 200
    assert response.data['theme_id'] == 'dark'


@pytest.mark.django_db
def test_admin_theme_put_invalid_theme_id(staff_client):
    """PUT with unknown theme_id returns 400 with field-level error on theme_id."""
    url = reverse('admin-theme')
    response = staff_client.put(url, {'theme_id': 'pokemon'}, format='json')
    assert response.status_code == 400
    assert 'theme_id' in response.data


@pytest.mark.django_db
def test_admin_theme_put_invalid_hex(staff_client):
    """PUT with invalid hex value in custom_colors returns 400 with field error."""
    url = reverse('admin-theme')
    payload = {'custom_colors': {'--color-primary': 'notahex'}}
    response = staff_client.put(url, payload, format='json')
    assert response.status_code == 400
    assert 'custom_colors' in response.data


@pytest.mark.django_db
def test_admin_theme_put_invalid_color_key(staff_client):
    """PUT with a disallowed CSS variable key returns 400 with field error."""
    url = reverse('admin-theme')
    payload = {'custom_colors': {'--hacker': '#ff0000'}}
    response = staff_client.put(url, payload, format='json')
    assert response.status_code == 400
    assert 'custom_colors' in response.data


@pytest.mark.django_db
def test_admin_theme_put_custom_colors_not_dict(staff_client):
    """PUT with custom_colors as a list (not dict) returns 400."""
    url = reverse('admin-theme')
    payload = {'custom_colors': ['#ff0000']}
    response = staff_client.put(url, payload, format='json')
    assert response.status_code == 400
    assert 'custom_colors' in response.data


@pytest.mark.django_db
def test_admin_theme_put_valid_hex_8char(staff_client):
    """PUT with 8-character hex (#RRGGBBAA) is accepted."""
    url = reverse('admin-theme')
    payload = {'custom_colors': {'--color-primary': '#FF6B35CC'}}
    response = staff_client.put(url, payload, format='json')
    assert response.status_code == 200
    assert response.data['custom_colors']['--color-primary'] == '#FF6B35CC'


# ---------------------------------------------------------------------------
# Cache invalidation
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_admin_theme_put_invalidates_cache(staff_client):
    """After a successful PUT, the cache key is deleted."""
    from django.core.cache import cache
    # Seed the cache manually
    cache.set(SITE_THEME_CACHE_KEY, {'theme_id': 'classic', 'custom_colors': {}}, 60)
    assert cache.get(SITE_THEME_CACHE_KEY) is not None

    url = reverse('admin-theme')
    staff_client.put(url, {'theme_id': 'elegant'}, format='json')

    assert cache.get(SITE_THEME_CACHE_KEY) is None


# ---------------------------------------------------------------------------
# Reset endpoint
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_admin_theme_reset(staff_client):
    """POST /reset/ clears custom_colors to {} while preserving theme_id."""
    # Set up a theme with custom colors
    theme = SiteTheme.objects.get(pk=1)
    theme.theme_id = 'dark'
    theme.custom_colors = {'--color-primary': '#ffffff'}
    theme.save()

    url = reverse('admin-theme-reset')
    response = staff_client.post(url, {}, format='json')
    assert response.status_code == 200
    assert response.data['custom_colors'] == {}
    assert response.data['theme_id'] == 'dark'  # theme_id unchanged

    theme.refresh_from_db()
    assert theme.custom_colors == {}
    assert theme.theme_id == 'dark'


@pytest.mark.django_db
def test_admin_theme_reset_requires_staff(regular_client):
    """Non-staff user gets 403 on POST /reset/."""
    url = reverse('admin-theme-reset')
    response = regular_client.post(url, {}, format='json')
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# Singleton invariant
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_singleton_invariant():
    """
    Saving SiteTheme via load() twice with different theme_ids results in only
    one row (pk=1) in the database; the second save overwrites the first.
    """
    theme_a = SiteTheme.load()
    theme_a.theme_id = 'dark'
    theme_a.save()
    assert SiteTheme.objects.get(pk=1).theme_id == 'dark'

    theme_b = SiteTheme.load()
    theme_b.theme_id = 'elegant'
    theme_b.save()
    assert SiteTheme.objects.count() == 1
    assert SiteTheme.objects.get(pk=1).theme_id == 'elegant'
