"""Tests for UserDataExportView."""
import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

User = get_user_model()


@pytest.fixture
def user(db):
    return User.objects.create_user(
        username='exportuser',
        email='export@test.com',
        password='testpassword123',
        first_name='Export',
        last_name='User',
    )


@pytest.fixture
def auth_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.mark.django_db
class TestUserDataExport:
    url = '/api/users/me/export/'

    def test_returns_user_data_with_correct_password(self, auth_client):
        resp = auth_client.get(self.url, HTTP_X_CONFIRM_PASSWORD='testpassword123')
        assert resp.status_code == 200
        data = resp.data
        assert data['user']['email'] == 'export@test.com'
        assert 'addresses' in data
        assert 'orders' in data
        assert 'reviews' in data
        assert 'wishlist' in data

    def test_requires_confirm_password_header(self, auth_client):
        resp = auth_client.get(self.url)
        assert resp.status_code == 400
        assert resp.data['type'] == 'confirmation_required'

    def test_wrong_password_returns_400(self, auth_client):
        resp = auth_client.get(self.url, HTTP_X_CONFIRM_PASSWORD='wrongpassword')
        assert resp.status_code == 400
        assert resp.data['type'] == 'invalid_password'

    def test_requires_authentication(self):
        client = APIClient()
        resp = client.get(self.url, HTTP_X_CONFIRM_PASSWORD='any')
        assert resp.status_code == 401
