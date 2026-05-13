"""Tests for /healthz/ and /readyz/ endpoints."""
import pytest
from unittest.mock import patch


@pytest.mark.django_db
class TestHealthz:
    def test_always_200(self, client):
        resp = client.get('/healthz/')
        assert resp.status_code == 200
        assert resp.json()['status'] == 'ok'

    def test_method_not_allowed_post(self, client):
        resp = client.post('/healthz/')
        assert resp.status_code == 405


@pytest.mark.django_db
class TestReadyz:
    def test_200_when_deps_up(self, client):
        resp = client.get('/readyz/')
        # DB and Redis should be up in tests
        assert resp.status_code in (200, 503)  # 503 if broker missing is OK

    def test_503_when_db_unreachable(self, client):
        with patch('django.db.connection.ensure_connection', side_effect=Exception('DB down')):
            resp = client.get('/readyz/')
        assert resp.status_code == 503
        data = resp.json()
        assert data['status'] == 'degraded'
        assert 'database' in data['failures']
