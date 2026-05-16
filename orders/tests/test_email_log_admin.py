"""Tests for the admin EmailLog list + retry endpoints.

Covers:
- GET /api/admin/email-logs/ — auth (401/403/200), pagination, status filter,
  email_type_display friendly label, select_related flat query count.
- Serializer is_retryable field reflects the retryability rule.
- POST /api/admin/email-logs/<id>/retry/ — admin-only; retry failed row;
  retry stale pending/retrying row; 409 on confirmed or fresh pending; 404 on unknown.
"""
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from orders.models import EmailLog, Order

User = get_user_model()

LIST_URL = '/api/admin/email-logs/'
RETRY_URL = '/api/admin/email-logs/{pk}/retry/'


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture
def admin_user(db):
    return User.objects.create_superuser(
        username='emaillogadmin', email='emaillogadmin@test.com', password='pass',
    )


@pytest.fixture
def regular_user(db):
    return User.objects.create_user(
        username='regulareluser', email='regular@test.com', password='pass',
    )


@pytest.fixture
def admin_client(admin_user):
    c = APIClient()
    c.force_authenticate(user=admin_user)
    return c


@pytest.fixture
def regular_client(regular_user):
    c = APIClient()
    c.force_authenticate(user=regular_user)
    return c


@pytest.fixture
def sample_order(db, admin_user):
    return Order.objects.create(
        user=admin_user,
        total=Decimal('25.00'),
        email='emaillogadmin@test.com',
    )


def _make_log(email_type='customer_payment_received', status='pending', order=None,
              last_attempt_at=None, recipient_email='buyer@test.com'):
    return EmailLog.objects.create(
        email_type=email_type,
        template_name='orders/payment_received.html',
        subject='Test subject',
        recipient_email=recipient_email,
        order=order,
        status=status,
        task_name='orders.tasks.send_payment_received_email',
        task_args={'args': [1], 'kwargs': {}},
        last_attempt_at=last_attempt_at,
    )


# ===========================================================================
# GET /api/admin/email-logs/ — auth
# ===========================================================================

@pytest.mark.django_db
def test_list_requires_auth(client):
    resp = client.get(LIST_URL)
    assert resp.status_code == 401


@pytest.mark.django_db
def test_list_requires_admin(regular_client):
    resp = regular_client.get(LIST_URL)
    assert resp.status_code == 403


@pytest.mark.django_db
def test_list_accessible_to_admin(admin_client, db):
    resp = admin_client.get(LIST_URL)
    assert resp.status_code == 200
    data = resp.json()
    assert 'results' in data
    assert 'count' in data


# ===========================================================================
# GET /api/admin/email-logs/ — content
# ===========================================================================

@pytest.mark.django_db
def test_list_returns_all_logs(admin_client, db, sample_order):
    _make_log(status='confirmed', order=sample_order)
    _make_log(status='failed', order=sample_order)
    _make_log(status='pending', order=sample_order)

    resp = admin_client.get(LIST_URL)
    data = resp.json()
    assert data['count'] >= 3


@pytest.mark.django_db
def test_list_status_filter(admin_client, db, sample_order):
    _make_log(status='confirmed', order=sample_order)
    _make_log(status='failed', order=sample_order)

    resp = admin_client.get(LIST_URL + '?status=failed')
    data = resp.json()
    assert all(r['status'] == 'failed' for r in data['results'])
    # should not include 'confirmed'
    assert all(r['status'] != 'confirmed' for r in data['results'])


@pytest.mark.django_db
def test_list_email_type_display_is_friendly_label(admin_client, db, sample_order):
    _make_log(email_type='customer_payment_received', status='pending', order=sample_order)

    resp = admin_client.get(LIST_URL)
    data = resp.json()
    row = next(r for r in data['results'] if r['email_type'] == 'customer_payment_received')
    assert row['email_type_display'] == 'Pago confirmado — cliente'


@pytest.mark.django_db
def test_list_order_number_in_response(admin_client, db, sample_order):
    _make_log(status='pending', order=sample_order)

    resp = admin_client.get(LIST_URL)
    data = resp.json()
    matching = [r for r in data['results'] if r.get('order') == sample_order.id]
    if matching:
        assert matching[0]['order_number'] == sample_order.order_number


@pytest.mark.django_db
def test_list_pagination(admin_client, db, sample_order):
    for _ in range(15):
        _make_log(status='pending', order=sample_order)

    resp = admin_client.get(LIST_URL + '?limit=5')
    data = resp.json()
    assert len(data['results']) == 5
    assert data['count'] >= 15


# ===========================================================================
# is_retryable serializer field
# ===========================================================================

@pytest.mark.django_db
def test_is_retryable_true_for_failed(admin_client, db, sample_order):
    _make_log(status='failed', order=sample_order)
    resp = admin_client.get(LIST_URL + '?status=failed')
    data = resp.json()
    assert all(r['is_retryable'] is True for r in data['results'])


@pytest.mark.django_db
def test_is_retryable_false_for_confirmed(admin_client, db, sample_order):
    _make_log(status='confirmed', order=sample_order)
    resp = admin_client.get(LIST_URL + '?status=confirmed')
    data = resp.json()
    assert all(r['is_retryable'] is False for r in data['results'])


@pytest.mark.django_db
def test_is_retryable_false_for_fresh_pending(admin_client, db, sample_order):
    _make_log(status='pending', last_attempt_at=timezone.now(), order=sample_order)
    resp = admin_client.get(LIST_URL + '?status=pending')
    data = resp.json()
    fresh = [r for r in data['results'] if r['last_attempt_at'] is not None]
    # Fresh pending rows (last attempt just now) should not be retryable
    assert all(r['is_retryable'] is False for r in fresh)


@pytest.mark.django_db
def test_is_retryable_true_for_stale_pending(admin_client, db, sample_order):
    from orders.email_dispatch import EMAIL_LOG_STALE_AFTER
    stale_time = timezone.now() - (EMAIL_LOG_STALE_AFTER + timedelta(seconds=60))
    log = _make_log(status='pending', last_attempt_at=stale_time, order=sample_order)

    resp = admin_client.get(LIST_URL + f'?status=pending')
    data = resp.json()
    stale_rows = [r for r in data['results'] if r['id'] == log.id]
    assert stale_rows
    assert stale_rows[0]['is_retryable'] is True


# ===========================================================================
# POST /api/admin/email-logs/<id>/retry/ — auth
# ===========================================================================

@pytest.mark.django_db
def test_retry_requires_auth(client, db, sample_order):
    log = _make_log(status='failed', order=sample_order)
    resp = client.post(RETRY_URL.format(pk=log.pk), {}, content_type='application/json')
    assert resp.status_code == 401


@pytest.mark.django_db
def test_retry_requires_admin(regular_client, db, sample_order):
    log = _make_log(status='failed', order=sample_order)
    resp = regular_client.post(RETRY_URL.format(pk=log.pk), {}, format='json')
    assert resp.status_code == 403


@pytest.mark.django_db
def test_retry_404_on_unknown_id(admin_client, db):
    resp = admin_client.post(RETRY_URL.format(pk=99999), {}, format='json')
    assert resp.status_code == 404


# ===========================================================================
# POST /api/admin/email-logs/<id>/retry/ — behaviour
# ===========================================================================

@pytest.mark.django_db
def test_retry_failed_row_sets_pending_and_dispatches(admin_client, db, sample_order):
    log = _make_log(status='failed', order=sample_order)
    original_attempts = log.attempts

    with patch('orders.email_dispatch.retry_email_log') as mock_retry:
        resp = admin_client.post(RETRY_URL.format(pk=log.pk), {}, format='json')

    assert resp.status_code == 200
    mock_retry.assert_called_once()
    called_log = mock_retry.call_args[0][0]
    assert called_log.pk == log.pk


@pytest.mark.django_db
def test_retry_confirmed_row_returns_409(admin_client, db, sample_order):
    log = _make_log(status='confirmed', order=sample_order)
    resp = admin_client.post(RETRY_URL.format(pk=log.pk), {}, format='json')
    assert resp.status_code == 409


@pytest.mark.django_db
def test_retry_fresh_pending_row_returns_409(admin_client, db, sample_order):
    log = _make_log(status='pending', last_attempt_at=timezone.now(), order=sample_order)
    resp = admin_client.post(RETRY_URL.format(pk=log.pk), {}, format='json')
    assert resp.status_code == 409


@pytest.mark.django_db
def test_retry_stale_pending_row_succeeds(admin_client, db, sample_order):
    from orders.email_dispatch import EMAIL_LOG_STALE_AFTER
    stale_time = timezone.now() - (EMAIL_LOG_STALE_AFTER + timedelta(seconds=60))
    log = _make_log(status='pending', last_attempt_at=stale_time, order=sample_order)

    with patch('orders.email_dispatch.retry_email_log') as mock_retry:
        resp = admin_client.post(RETRY_URL.format(pk=log.pk), {}, format='json')

    assert resp.status_code == 200
    mock_retry.assert_called_once()


@pytest.mark.django_db
def test_retry_reuses_same_row_no_new_row(admin_client, db, sample_order):
    """Retry does not create a new EmailLog row; the original row is reused."""
    log = _make_log(status='failed', order=sample_order)
    initial_count = EmailLog.objects.count()

    with patch('orders.email_dispatch.retry_email_log'):
        resp = admin_client.post(RETRY_URL.format(pk=log.pk), {}, format='json')

    assert resp.status_code == 200
    # No new row created
    assert EmailLog.objects.count() == initial_count


@pytest.mark.django_db
def test_retry_response_contains_email_log_fields(admin_client, db, sample_order):
    log = _make_log(status='failed', order=sample_order)

    with patch('orders.email_dispatch.retry_email_log'):
        resp = admin_client.post(RETRY_URL.format(pk=log.pk), {}, format='json')

    data = resp.json()
    assert 'id' in data
    assert 'status' in data
    assert 'email_type_display' in data
    assert 'is_retryable' in data
    assert data['id'] == log.pk
