"""Tests for UserAccountDeleteView (GDPR soft-delete)."""
import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

User = get_user_model()


@pytest.fixture
def user(db):
    return User.objects.create_user(
        username='deleteuser',
        email='delete@test.com',
        password='testpassword123',
        first_name='Delete',
        last_name='Me',
    )


@pytest.fixture
def auth_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.mark.django_db
class TestUserAccountDelete:
    url = '/api/users/me/'

    def test_soft_delete_returns_204(self, auth_client):
        resp = auth_client.delete(self.url, HTTP_X_CONFIRM_PASSWORD='testpassword123')
        assert resp.status_code == 204

    def test_user_is_deactivated(self, user, auth_client):
        auth_client.delete(self.url, HTTP_X_CONFIRM_PASSWORD='testpassword123')
        user.refresh_from_db()
        assert user.is_active is False

    def test_email_is_anonymised(self, user, auth_client):
        user_id = user.pk
        auth_client.delete(self.url, HTTP_X_CONFIRM_PASSWORD='testpassword123')
        user.refresh_from_db()
        assert user.email == f'deleted-{user_id}@anonymized.local'

    def test_name_is_anonymised(self, user, auth_client):
        auth_client.delete(self.url, HTTP_X_CONFIRM_PASSWORD='testpassword123')
        user.refresh_from_db()
        assert user.first_name == 'Deleted'
        assert user.last_name == 'User'

    def test_requires_confirm_password_header(self, auth_client):
        resp = auth_client.delete(self.url)
        assert resp.status_code == 400
        assert resp.data['type'] == 'confirmation_required'

    def test_wrong_password_returns_400(self, auth_client):
        resp = auth_client.delete(self.url, HTTP_X_CONFIRM_PASSWORD='wrongpass')
        assert resp.status_code == 400
        assert resp.data['type'] == 'invalid_password'

    def test_requires_authentication(self):
        client = APIClient()
        resp = client.delete(self.url, HTTP_X_CONFIRM_PASSWORD='any')
        assert resp.status_code == 401

    def test_orders_are_preserved(self, user, auth_client, db):
        from orders.models import Order
        order = Order.objects.create(user=user, total='50.00')
        auth_client.delete(self.url, HTTP_X_CONFIRM_PASSWORD='testpassword123')
        # Order still exists
        assert Order.objects.filter(pk=order.pk).exists()
