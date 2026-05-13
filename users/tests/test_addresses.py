"""Tests for UserAddress CRUD endpoints."""
import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient

User = get_user_model()


@pytest.fixture
def user(db):
    return User.objects.create_user(
        username='testuser',
        email='test@example.com',
        password='securepassword123',
    )


@pytest.fixture
def auth_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def address_data():
    return {
        'label': 'Casa',
        'recipient_name': 'Juan Pérez',
        'phone': '+51 999 000 111',
        'street': 'Av. Javier Prado 1234',
        'city': 'Lima',
        'country': 'PE',
        'is_default_shipping': True,
        'is_default_billing': False,
    }


@pytest.mark.django_db
class TestUserAddressListCreate:
    url = '/api/users/me/addresses/'

    def test_list_returns_empty_for_new_user(self, auth_client):
        resp = auth_client.get(self.url)
        assert resp.status_code == 200
        assert resp.data == []

    def test_create_address_happy_path(self, auth_client, address_data):
        resp = auth_client.post(self.url, address_data, format='json')
        assert resp.status_code == 201
        assert resp.data['recipient_name'] == 'Juan Pérez'
        assert resp.data['city'] == 'Lima'

    def test_create_requires_auth(self, address_data):
        client = APIClient()
        resp = client.post(self.url, address_data, format='json')
        assert resp.status_code == 401

    def test_create_validates_required_fields(self, auth_client):
        resp = auth_client.post(self.url, {}, format='json')
        assert resp.status_code == 400
        assert 'field_errors' in resp.data

    def test_create_validates_recipient_name_blank(self, auth_client, address_data):
        address_data['recipient_name'] = '   '
        resp = auth_client.post(self.url, address_data, format='json')
        assert resp.status_code == 400
        assert 'recipient_name' in resp.data.get('field_errors', {})

    def test_list_returns_own_addresses_only(self, auth_client, address_data, db):
        other_user = User.objects.create_user(username='other', email='other@test.com', password='pass')
        from users.models import UserAddress
        UserAddress.objects.create(user=other_user, recipient_name='Other', street='X', city='Lima', country='PE')
        auth_client.post(self.url, address_data, format='json')
        resp = auth_client.get(self.url)
        assert len(resp.data) == 1
        assert resp.data[0]['recipient_name'] == 'Juan Pérez'


@pytest.mark.django_db
class TestUserAddressDetail:
    def _create_address(self, auth_client, data):
        resp = auth_client.post('/api/users/me/addresses/', data, format='json')
        assert resp.status_code == 201
        return resp.data['id']

    def test_get_own_address(self, auth_client, address_data):
        addr_id = self._create_address(auth_client, address_data)
        resp = auth_client.get(f'/api/users/me/addresses/{addr_id}/')
        assert resp.status_code == 200
        assert resp.data['id'] == addr_id

    def test_patch_address(self, auth_client, address_data):
        addr_id = self._create_address(auth_client, address_data)
        resp = auth_client.patch(f'/api/users/me/addresses/{addr_id}/', {'city': 'Arequipa'}, format='json')
        assert resp.status_code == 200
        assert resp.data['city'] == 'Arequipa'

    def test_delete_address(self, auth_client, address_data):
        addr_id = self._create_address(auth_client, address_data)
        resp = auth_client.delete(f'/api/users/me/addresses/{addr_id}/')
        assert resp.status_code == 200

    def test_cannot_access_other_users_address(self, auth_client, address_data, db):
        other_user = User.objects.create_user(username='other2', email='other2@test.com', password='pass')
        from users.models import UserAddress
        other_addr = UserAddress.objects.create(user=other_user, recipient_name='X', street='Y', city='Lima', country='PE')
        resp = auth_client.get(f'/api/users/me/addresses/{other_addr.pk}/')
        assert resp.status_code == 404

    def test_404_for_nonexistent_address(self, auth_client):
        resp = auth_client.get('/api/users/me/addresses/999999/')
        assert resp.status_code == 404


@pytest.mark.django_db
class TestUserAddressSetDefault:
    def test_set_default(self, auth_client, address_data):
        resp = auth_client.post('/api/users/me/addresses/', address_data, format='json')
        addr_id = resp.data['id']
        resp = auth_client.post(f'/api/users/me/addresses/{addr_id}/set-default/')
        assert resp.status_code == 200
        assert resp.data['is_default_shipping'] is True
        assert resp.data['is_default_billing'] is True

    def test_single_default_enforced(self, auth_client, address_data, db):
        from users.models import UserAddress
        resp1 = auth_client.post('/api/users/me/addresses/', address_data, format='json')
        addr_id1 = resp1.data['id']
        address_data['is_default_shipping'] = False
        resp2 = auth_client.post('/api/users/me/addresses/', address_data, format='json')
        addr_id2 = resp2.data['id']
        auth_client.post(f'/api/users/me/addresses/{addr_id1}/set-default/')
        auth_client.post(f'/api/users/me/addresses/{addr_id2}/set-default/')
        assert UserAddress.objects.filter(is_default_shipping=True).count() == 1
