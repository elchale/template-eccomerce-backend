"""Tests for OrderStateMachine."""
import pytest
from unittest.mock import patch
from django.contrib.auth import get_user_model

User = get_user_model()


@pytest.fixture
def user(db):
    return User.objects.create_user(username='smuser', email='sm@test.com', password='pass')


@pytest.fixture
def pending_order(user):
    from orders.models import Order
    order = Order.objects.create(user=user, total='100.00')
    return order


@pytest.mark.django_db
class TestOrderStateMachine:
    def test_valid_pending_to_confirmed(self, pending_order):
        from orders.services.state_machine import OrderStateMachine
        with patch('orders.email_dispatch.dispatch_order_email'):
            OrderStateMachine.transition(pending_order, 'confirmed')
        pending_order.refresh_from_db()
        assert pending_order.status == 'confirmed'

    def test_valid_pending_to_cancelled(self, pending_order):
        from orders.services.state_machine import OrderStateMachine
        with patch('orders.email_dispatch.dispatch_order_email'):
            OrderStateMachine.transition(pending_order, 'cancelled')
        pending_order.refresh_from_db()
        assert pending_order.status == 'cancelled'

    def test_invalid_pending_to_shipped(self, pending_order):
        from orders.services.state_machine import OrderStateMachine
        from orders.exceptions import InvalidTransition
        with pytest.raises(InvalidTransition):
            OrderStateMachine.transition(pending_order, 'shipped')

    def test_invalid_pending_to_delivered(self, pending_order):
        from orders.services.state_machine import OrderStateMachine
        from orders.exceptions import InvalidTransition
        with pytest.raises(InvalidTransition):
            OrderStateMachine.transition(pending_order, 'delivered')

    def test_terminal_cancelled_no_transition(self, pending_order):
        from orders.services.state_machine import OrderStateMachine
        from orders.exceptions import InvalidTransition
        with patch('orders.email_dispatch.dispatch_order_email'):
            OrderStateMachine.transition(pending_order, 'cancelled')
        pending_order.refresh_from_db()
        with pytest.raises(InvalidTransition):
            OrderStateMachine.transition(pending_order, 'confirmed')

    def test_transition_writes_history_row(self, pending_order, user):
        from orders.services.state_machine import OrderStateMachine
        from orders.models import OrderStatusHistory
        with patch('orders.email_dispatch.dispatch_order_email'):
            OrderStateMachine.transition(pending_order, 'confirmed', user=user, note='test note')
        history = OrderStatusHistory.objects.filter(order=pending_order).first()
        assert history is not None
        assert history.old_status == 'pending'
        assert history.new_status == 'confirmed'
        assert history.note == 'test note'

    def test_full_happy_path_pending_to_delivered(self, pending_order):
        from orders.services.state_machine import OrderStateMachine
        transitions = ['confirmed', 'shipped', 'delivered']
        for t in transitions:
            with patch('orders.email_dispatch.dispatch_order_email'):
                OrderStateMachine.transition(pending_order, t)
            pending_order.refresh_from_db()
            assert pending_order.status == t

    def test_confirmed_to_refunded(self, pending_order):
        from orders.services.state_machine import OrderStateMachine
        with patch('orders.email_dispatch.dispatch_order_email'):
            OrderStateMachine.transition(pending_order, 'confirmed')
        pending_order.refresh_from_db()
        with patch('orders.email_dispatch.dispatch_order_email'):
            OrderStateMachine.transition(pending_order, 'refunded')
        pending_order.refresh_from_db()
        assert pending_order.status == 'refunded'

    def test_dispatch_called_with_correct_args(self, pending_order, user):
        """dispatch_order_email is called with the right task and email_type."""
        from orders.services.state_machine import OrderStateMachine
        from orders.tasks import send_order_status_changed

        with patch('orders.email_dispatch.dispatch_order_email') as mock_dispatch:
            OrderStateMachine.transition(pending_order, 'confirmed', user=user)

        mock_dispatch.assert_called_once_with(
            send_order_status_changed,
            pending_order.id,
            'pending',
            'confirmed',
            changed_by_id=user.id,
            order_id=pending_order.id,
            email_type='customer_status_update',
        )


@pytest.mark.django_db
class TestAdminStatusUpdateView:
    url_template = '/api/admin/orders/{pk}/status/'

    def _get_url(self, pk):
        return self.url_template.format(pk=pk)

    def test_invalid_transition_returns_400(self, pending_order, db):
        from rest_framework.test import APIClient
        admin = User.objects.create_superuser(username='admin_sm', email='admin_sm@test.com', password='pass')
        client = APIClient()
        client.force_authenticate(user=admin)
        resp = client.patch(self._get_url(pending_order.pk), {'new_status': 'shipped'}, format='json')
        assert resp.status_code == 400
        assert resp.data.get('type') == 'invalid_transition'

    def test_valid_transition_returns_200(self, pending_order, db):
        from rest_framework.test import APIClient
        admin = User.objects.create_superuser(username='admin_sm2', email='admin_sm2@test.com', password='pass')
        client = APIClient()
        client.force_authenticate(user=admin)
        with patch('orders.email_dispatch.dispatch_order_email'):
            resp = client.patch(self._get_url(pending_order.pk), {'new_status': 'confirmed'}, format='json')
        assert resp.status_code == 200
        pending_order.refresh_from_db()
        assert pending_order.status == 'confirmed'
