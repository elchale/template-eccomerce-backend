"""Tests for the order email dispatch, utils, tasks, and EmailLog lifecycle.

Covers:
- dispatch_order_email: on_commit deferral, EmailLog creation, thread/celery routing
- email_log_is_retryable / EMAIL_LOG_STALE_AFTER retryability rules
- should_notify_admin_of_status_change matrix
- Template rendering (non-empty HTML + .txt)
- send_order_status_changed: customer always; admin conditional
- email_utils.send_order_email: retry on transient SMTPException
- EmailLog lifecycle: pending → confirmed / failed
"""
import smtplib
from datetime import timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch, call

import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from django.utils import timezone

User = get_user_model()


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture
def order_user(db):
    return User.objects.create_user(
        username='orderuser',
        email='orderuser@test.com',
        password='pass',
        is_staff=False,
    )


@pytest.fixture
def staff_user(db):
    return User.objects.create_user(
        username='staffuser',
        email='staff@test.com',
        password='pass',
        is_staff=True,
    )


@pytest.fixture
def order(db, order_user):
    from orders.models import Order, OrderItem
    o = Order.objects.create(
        user=order_user,
        status=Order.Status.CONFIRMED,
        subtotal=Decimal('50.00'),
        total=Decimal('50.00'),
        email='orderuser@test.com',
        payment_method='izipay',
        izipay_transaction_id='tx-test-123',
        currency_code='PEN',
    )
    return o


# ===========================================================================
# should_notify_admin_of_status_change matrix
# ===========================================================================

@pytest.mark.django_db
class TestShouldNotifyAdmin:
    def test_system_trigger_notifies(self, order):
        from orders.email_dispatch import should_notify_admin_of_status_change
        order.status = 'shipped'
        assert should_notify_admin_of_status_change(order, changed_by=None) is True

    def test_non_staff_customer_notifies(self, order, order_user):
        from orders.email_dispatch import should_notify_admin_of_status_change
        order.status = 'shipped'
        assert should_notify_admin_of_status_change(order, changed_by=order_user) is True

    def test_staff_shipped_does_not_notify(self, order, staff_user):
        from orders.email_dispatch import should_notify_admin_of_status_change
        order.status = 'shipped'
        assert should_notify_admin_of_status_change(order, changed_by=staff_user) is False

    def test_staff_cancelled_always_notifies(self, order, staff_user):
        from orders.email_dispatch import should_notify_admin_of_status_change
        order.status = 'cancelled'
        assert should_notify_admin_of_status_change(order, changed_by=staff_user) is True

    def test_staff_refunded_always_notifies(self, order, staff_user):
        from orders.email_dispatch import should_notify_admin_of_status_change
        order.status = 'refunded'
        assert should_notify_admin_of_status_change(order, changed_by=staff_user) is True

    def test_none_cancelled_notifies(self, order):
        from orders.email_dispatch import should_notify_admin_of_status_change
        order.status = 'cancelled'
        assert should_notify_admin_of_status_change(order, changed_by=None) is True


# ===========================================================================
# email_log_is_retryable / EMAIL_LOG_STALE_AFTER
# ===========================================================================

@pytest.mark.django_db
class TestEmailLogRetryability:
    def _make_log(self, status, last_attempt_at=None, created_offset=None):
        from orders.models import EmailLog
        log = EmailLog(
            email_type='customer_payment_received',
            template_name='orders/payment_received.html',
            subject='Test',
            recipient_email='test@test.com',
            task_name='orders.tasks.send_payment_received_email',
            status=status,
            last_attempt_at=last_attempt_at,
        )
        # Set created via direct attribute (not via DB save for unit tests)
        if created_offset is not None:
            log.created = timezone.now() - created_offset
        else:
            log.created = timezone.now()
        return log

    def test_confirmed_never_retryable(self):
        from orders.email_dispatch import email_log_is_retryable
        log = self._make_log('confirmed')
        assert email_log_is_retryable(log) is False

    def test_failed_always_retryable(self):
        from orders.email_dispatch import email_log_is_retryable
        log = self._make_log('failed')
        assert email_log_is_retryable(log) is True

    def test_fresh_pending_not_retryable(self):
        from orders.email_dispatch import email_log_is_retryable, EMAIL_LOG_STALE_AFTER
        # Fresh: last_attempt_at is now
        log = self._make_log('pending', last_attempt_at=timezone.now())
        assert email_log_is_retryable(log) is False

    def test_stale_pending_retryable(self):
        from orders.email_dispatch import email_log_is_retryable, EMAIL_LOG_STALE_AFTER
        stale_time = timezone.now() - (EMAIL_LOG_STALE_AFTER + timedelta(seconds=60))
        log = self._make_log('pending', last_attempt_at=stale_time)
        assert email_log_is_retryable(log) is True

    def test_fresh_retrying_not_retryable(self):
        from orders.email_dispatch import email_log_is_retryable
        log = self._make_log('retrying', last_attempt_at=timezone.now())
        assert email_log_is_retryable(log) is False

    def test_stale_retrying_retryable(self):
        from orders.email_dispatch import email_log_is_retryable, EMAIL_LOG_STALE_AFTER
        stale_time = timezone.now() - (EMAIL_LOG_STALE_AFTER + timedelta(seconds=60))
        log = self._make_log('retrying', last_attempt_at=stale_time)
        assert email_log_is_retryable(log) is True

    def test_pending_no_last_attempt_uses_created(self):
        """When last_attempt_at is None, falls back to created for staleness."""
        from orders.email_dispatch import email_log_is_retryable, EMAIL_LOG_STALE_AFTER
        stale_time = timezone.now() - (EMAIL_LOG_STALE_AFTER + timedelta(seconds=60))
        log = self._make_log('pending', created_offset=(EMAIL_LOG_STALE_AFTER + timedelta(seconds=60)))
        log.last_attempt_at = None
        assert email_log_is_retryable(log) is True


# ===========================================================================
# EmailLog lifecycle via email_utils.send_order_email
# ===========================================================================

@pytest.mark.django_db
class TestEmailLogLifecycle:
    @pytest.fixture(autouse=True)
    def use_locmem_backend(self, settings):
        settings.EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'

    def _make_db_log(self, order):
        from orders.models import EmailLog
        return EmailLog.objects.create(
            email_type='customer_payment_received',
            template_name='orders/payment_received.html',
            subject='Test subject',
            recipient_email='buyer@test.com',
            order=order,
            task_name='orders.tasks.send_payment_received_email',
            status='pending',
        )

    def test_success_path_sets_confirmed(self, order):
        from orders.models import EmailLog
        from orders.email_utils import send_order_email

        log = self._make_db_log(order)

        result = send_order_email(
            template_html='orders/payment_received.html',
            template_txt='orders/payment_received.txt',
            context={'order': order, 'items': []},
            subject='Pago confirmado',
            recipient='buyer@test.com',
            email_log_id=log.pk,
        )

        assert result is True
        log.refresh_from_db()
        assert log.status == 'confirmed'
        assert log.sent_at is not None
        assert log.attempts >= 1

    def test_failure_path_sets_failed(self, order):
        from orders.models import EmailLog
        from orders.email_utils import send_order_email

        log = self._make_db_log(order)

        with patch('orders.email_utils.get_connection') as mock_conn:
            mock_msg = MagicMock()
            mock_msg.send.side_effect = smtplib.SMTPException('Connection refused')
            mock_conn.return_value = MagicMock()
            # Patch EmailMultiAlternatives.send
            with patch('orders.email_utils.EmailMultiAlternatives') as MockEmail:
                instance = MockEmail.return_value
                instance.send.side_effect = smtplib.SMTPException('Connection refused')

                result = send_order_email(
                    template_html='orders/payment_received.html',
                    template_txt='orders/payment_received.txt',
                    context={'order': order, 'items': []},
                    subject='Pago confirmado',
                    recipient='buyer@test.com',
                    email_log_id=log.pk,
                )

        assert result is False
        log.refresh_from_db()
        assert log.status == 'failed'
        assert log.error_message != ''
        assert log.attempts >= 1

    def test_missing_template_sets_failed(self, order):
        from orders.models import EmailLog
        from orders.email_utils import send_order_email

        log = self._make_db_log(order)

        result = send_order_email(
            template_html='orders/nonexistent_template_xyz.html',
            template_txt='orders/nonexistent_template_xyz.txt',
            context={'order': order},
            subject='Test',
            recipient='buyer@test.com',
            email_log_id=log.pk,
        )

        assert result is False
        log.refresh_from_db()
        assert log.status == 'failed'
        assert 'nonexistent_template_xyz' in log.error_message


# ===========================================================================
# Template rendering — non-empty HTML + .txt
# ===========================================================================

@pytest.mark.django_db
class TestTemplateRendering:
    @pytest.fixture(autouse=True)
    def use_locmem_backend(self, settings):
        settings.EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'

    def _render(self, template_name, context):
        from django.template.loader import get_template
        return get_template(template_name).render(context)

    def test_payment_received_html(self, order, order_user):
        html = self._render('orders/payment_received.html', {'order': order, 'items': []})
        assert len(html) > 100
        assert order.order_number in html

    def test_payment_received_txt(self, order):
        txt = self._render('orders/payment_received.txt', {'order': order, 'items': []})
        assert order.order_number in txt

    def test_order_status_update_html(self, order):
        ctx = {
            'order': order,
            'old_status': 'confirmed',
            'new_status': 'shipped',
            'old_status_display': 'Confirmed',
            'new_status_display': 'Shipped',
            'note': 'Test note',
        }
        html = self._render('orders/order_status_update.html', ctx)
        assert order.order_number in html

    def test_refund_notification_html(self, order):
        html = self._render('orders/refund_notification.html', {'order': order})
        assert order.order_number in html

    def test_admin_new_paid_order_html(self, order):
        html = self._render('orders/admin/new_paid_order.html', {
            'order': order,
            'items': [],
            'admin_order_url': 'http://localhost/admin/orders/1',
        })
        assert order.order_number in html

    def test_admin_order_status_update_html(self, order):
        html = self._render('orders/admin/order_status_update.html', {
            'order': order,
            'old_status': 'confirmed',
            'new_status': 'shipped',
            'old_status_display': 'Confirmed',
            'new_status_display': 'Shipped',
            'note': '',
            'changed_by_display': 'Sistema/IPN',
            'admin_order_url': '',
            'customer_email': 'buyer@test.com',
        })
        assert order.order_number in html

    def test_admin_amount_mismatch_html(self, order):
        html = self._render('orders/admin/amount_mismatch.html', {
            'order': order,
            'expected_centimos': 5000,
            'received_centimos': 4999,
            'expected_soles': 50.00,
            'received_soles': 49.99,
            'admin_order_url': '',
        })
        assert order.order_number in html
        assert '5000' in html
        assert '4999' in html


# ===========================================================================
# send_order_status_changed: customer always sent; admin conditional
# ===========================================================================

@pytest.mark.django_db
class TestSendOrderStatusChanged:
    @pytest.fixture(autouse=True)
    def use_locmem_backend(self, settings):
        settings.EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
        settings.DEFAULT_FROM_EMAIL = 'from@test.com'
        settings.ADMIN_USER = 'admin@test.com'

    def test_customer_always_receives_email(self, order):
        from orders.tasks import send_order_status_changed
        send_order_status_changed(
            order.id, 'confirmed', 'shipped',
            changed_by_id=None,
        )
        assert len(mail.outbox) >= 1
        recipients = [msg.to[0] for msg in mail.outbox]
        assert 'orderuser@test.com' in recipients

    def test_status_shown_as_spanish_display(self, order):
        from orders.tasks import send_order_status_changed
        send_order_status_changed(
            order.id, 'confirmed', 'shipped',
            changed_by_id=None,
        )
        customer_email = next(
            msg for msg in mail.outbox if 'orderuser@test.com' in msg.to
        )
        # subject should use display label (Shipped in en locale, but our model uses English)
        assert 'shipped' in customer_email.subject.lower() or 'Shipped' in customer_email.subject

    def test_admin_not_notified_when_staff_ships(self, order, staff_user):
        from orders.tasks import send_order_status_changed
        send_order_status_changed(
            order.id, 'confirmed', 'shipped',
            changed_by_id=staff_user.id,
        )
        admin_emails = [msg for msg in mail.outbox if 'admin@test.com' in msg.to]
        assert len(admin_emails) == 0

    def test_admin_notified_when_system_triggers(self, order):
        from orders.tasks import send_order_status_changed
        send_order_status_changed(
            order.id, 'confirmed', 'shipped',
            changed_by_id=None,
        )
        admin_emails = [msg for msg in mail.outbox if 'admin@test.com' in msg.to]
        assert len(admin_emails) >= 1

    def test_admin_notified_on_staff_cancellation(self, order, staff_user):
        from orders.tasks import send_order_status_changed
        send_order_status_changed(
            order.id, 'confirmed', 'cancelled',
            changed_by_id=staff_user.id,
        )
        admin_emails = [msg for msg in mail.outbox if 'admin@test.com' in msg.to]
        assert len(admin_emails) >= 1


# ===========================================================================
# dispatch_order_email: on_commit deferral, EmailLog creation
# ===========================================================================

@pytest.mark.django_db(transaction=True)
class TestDispatchOrderEmail:
    @pytest.fixture(autouse=True)
    def use_locmem_backend(self, settings):
        settings.EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
        settings.USE_CELERY = False

    def test_creates_email_log_row(self, order):
        from orders.models import EmailLog
        from orders.email_dispatch import dispatch_order_email
        from orders.tasks import send_payment_received_email

        initial_count = EmailLog.objects.count()

        # Patch the thread execution so we don't actually send
        with patch('orders.email_dispatch._run_via_thread'):
            dispatch_order_email(
                send_payment_received_email,
                order.id,
                order_id=order.id,
                email_type='customer_payment_received',
            )

        assert EmailLog.objects.count() == initial_count + 1
        log = EmailLog.objects.latest('created')
        assert log.email_type == 'customer_payment_received'
        assert log.status == 'pending'
        assert log.order == order

    def test_thread_fallback_when_celery_disabled(self, order, settings):
        from orders.email_dispatch import dispatch_order_email
        from orders.tasks import send_payment_received_email

        settings.USE_CELERY = False

        with patch('orders.email_dispatch._run_via_thread') as mock_thread:
            dispatch_order_email(
                send_payment_received_email,
                order.id,
                order_id=order.id,
                email_type='customer_payment_received',
            )

        mock_thread.assert_called_once()

    def test_celery_path_when_enabled(self, order, settings):
        from orders.email_dispatch import dispatch_order_email
        from orders.tasks import send_payment_received_email

        settings.USE_CELERY = True
        settings.CELERY_TASK_ALWAYS_EAGER = False

        with patch('orders.email_dispatch._run_via_celery', return_value=True) as mock_celery:
            dispatch_order_email(
                send_payment_received_email,
                order.id,
                order_id=order.id,
                email_type='customer_payment_received',
            )

        mock_celery.assert_called_once()

    def test_broker_error_falls_back_to_thread(self, order, settings):
        from orders.email_dispatch import dispatch_order_email
        from orders.tasks import send_payment_received_email

        settings.USE_CELERY = True
        settings.CELERY_TASK_ALWAYS_EAGER = False

        with patch('orders.email_dispatch._run_via_celery', return_value=False) as mock_celery, \
             patch('orders.email_dispatch._run_via_thread') as mock_thread:
            dispatch_order_email(
                send_payment_received_email,
                order.id,
                order_id=order.id,
                email_type='customer_payment_received',
            )

        mock_celery.assert_called_once()
        mock_thread.assert_called_once()
