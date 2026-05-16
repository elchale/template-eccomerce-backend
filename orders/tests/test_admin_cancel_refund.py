"""Tests for the admin cancel-with-reason + refund endpoints."""
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from orders.models import Order, OrderStatusHistory, Refund

User = get_user_model()


@pytest.fixture
def admin(db):
    return User.objects.create_superuser(
        username='admincan', email='admincan@test.com', password='pass',
    )


@pytest.fixture
def admin_client(admin):
    client = APIClient()
    client.force_authenticate(user=admin)
    return client


@pytest.fixture
def paid_order(db, paid_user):
    order = Order.objects.create(
        user=paid_user,
        status=Order.Status.CONFIRMED,
        subtotal=Decimal('10.00'),
        total=Decimal('10.00'),
        payment_status='paid',
        izipay_transaction_id='tx-uuid-123',
        email='buyer@test.com',
    )
    return order


@pytest.fixture
def pending_unpaid_order(db, paid_user):
    return Order.objects.create(
        user=paid_user,
        status=Order.Status.PENDING,
        subtotal=Decimal('5.00'),
        total=Decimal('5.00'),
        payment_status='unpaid',
        email='buyer@test.com',
    )


@pytest.fixture(autouse=True)
def mock_dispatch():
    """Patch dispatch_order_email for all tests in this module so no SMTP / Celery calls."""
    with patch('orders.email_dispatch.dispatch_order_email') as m:
        yield m


@pytest.mark.django_db
class TestAdminCancelWithReason:
    def test_cancel_requires_reason(self, admin_client, pending_unpaid_order):
        url = f'/api/admin/orders/{pending_unpaid_order.pk}/status/'
        resp = admin_client.patch(url, {'new_status': 'cancelled'}, format='json')
        assert resp.status_code == 400
        body = resp.json()
        # DRF's custom exception handler wraps validation errors under
        # `field_errors`; the per-field key is `cancel_reason`.
        field_errors = body.get('field_errors') or body
        assert 'cancel_reason' in field_errors

    def test_cancel_with_reason_succeeds_and_logs_history(
        self, admin_client, pending_unpaid_order,
    ):
        url = f'/api/admin/orders/{pending_unpaid_order.pk}/status/'
        resp = admin_client.patch(
            url,
            {'new_status': 'cancelled', 'cancel_reason': 'Customer requested by phone'},
            format='json',
        )
        assert resp.status_code == 200
        pending_unpaid_order.refresh_from_db()
        assert pending_unpaid_order.status == 'cancelled'
        # Reason is prefixed in the audit note so the customer can see it.
        latest = OrderStatusHistory.objects.filter(order=pending_unpaid_order).order_by('-created').first()
        assert 'Customer requested by phone' in latest.note
        assert 'Motivo de cancelación' in latest.note

    def test_cancel_does_not_auto_refund_paid_orders(self, admin_client, paid_order):
        """Cancelling a paid order leaves payment_status='paid' — the admin
        must run /refund/ separately so refund failures are surfaced cleanly."""
        url = f'/api/admin/orders/{paid_order.pk}/status/'
        # paid_order.status is CONFIRMED; CONFIRMED → CANCELLED is allowed.
        with patch('orders.views.orders.cancel_or_refund') as gateway:
            resp = admin_client.patch(
                url,
                {'new_status': 'cancelled', 'cancel_reason': 'admin error'},
                format='json',
            )
        assert resp.status_code == 200
        gateway.assert_not_called()  # refund stays admin-driven
        paid_order.refresh_from_db()
        assert paid_order.status == 'cancelled'
        assert paid_order.payment_status == 'paid'

    def test_non_cancel_transitions_do_not_need_reason(self, admin_client, pending_unpaid_order):
        url = f'/api/admin/orders/{pending_unpaid_order.pk}/status/'
        resp = admin_client.patch(url, {'new_status': 'confirmed'}, format='json')
        assert resp.status_code == 200


@pytest.mark.django_db
class TestAdminRefund:
    def _gateway_ok(self):
        return {
            'status': 'SUCCESS',
            'answer': {'transactions': [{'uuid': 'refund-uuid-1'}]},
        }

    def test_refund_requires_reason(self, admin_client, paid_order):
        url = f'/api/admin/orders/{paid_order.pk}/refund/'
        resp = admin_client.post(url, {}, format='json')
        assert resp.status_code == 400

    def test_refund_full_amount_marks_order_refunded(self, admin_client, paid_order):
        url = f'/api/admin/orders/{paid_order.pk}/refund/'
        with patch('orders.views.orders.cancel_or_refund', return_value=self._gateway_ok()):
            resp = admin_client.post(
                url, {'reason': 'damaged in transit'}, format='json',
            )
        assert resp.status_code == 200
        paid_order.refresh_from_db()
        assert paid_order.payment_status == 'refunded'
        refund = Refund.objects.get(order=paid_order)
        assert refund.amount == paid_order.total
        assert refund.reason == 'damaged in transit'
        assert refund.status == Refund.RefundStatus.PROCESSED
        assert refund.external_refund_id == 'refund-uuid-1'

    def test_refund_rejects_unpaid_orders(self, admin_client, pending_unpaid_order):
        url = f'/api/admin/orders/{pending_unpaid_order.pk}/refund/'
        resp = admin_client.post(url, {'reason': 'oops'}, format='json')
        assert resp.status_code == 400
        assert Refund.objects.filter(order=pending_unpaid_order).count() == 0

    def test_partial_refund_preserves_paid_status(self, admin_client, paid_order):
        url = f'/api/admin/orders/{paid_order.pk}/refund/'
        with patch('orders.views.orders.cancel_or_refund', return_value=self._gateway_ok()):
            resp = admin_client.post(
                url, {'reason': 'partial', 'amount': '4.00'}, format='json',
            )
        assert resp.status_code == 200
        paid_order.refresh_from_db()
        # 4.00 < 10.00 → still partly paid, payment_status stays 'paid'
        assert paid_order.payment_status == 'paid'

    def test_double_full_refund_rejected(self, admin_client, paid_order):
        url = f'/api/admin/orders/{paid_order.pk}/refund/'
        with patch('orders.views.orders.cancel_or_refund', return_value=self._gateway_ok()):
            r1 = admin_client.post(url, {'reason': 'first'}, format='json')
            r2 = admin_client.post(url, {'reason': 'second'}, format='json')
        assert r1.status_code == 200
        assert r2.status_code == 400  # nothing left to refund

    def test_refund_gateway_failure_writes_no_row(self, admin_client, paid_order):
        from orders.izipay import IzipayError
        url = f'/api/admin/orders/{paid_order.pk}/refund/'
        with patch('orders.views.orders.cancel_or_refund', side_effect=IzipayError('Gateway down')):
            resp = admin_client.post(url, {'reason': 'attempt'}, format='json')
        assert resp.status_code == 400
        assert Refund.objects.filter(order=paid_order).count() == 0
        paid_order.refresh_from_db()
        assert paid_order.payment_status == 'paid'
