"""Central email dispatch helper for all order lifecycle emails.

Usage (all call sites):
    dispatch_order_email(task, *args, order_id=None, email_type=None, **kwargs)

Guarantees:
- Creates an EmailLog row in 'pending' before any send attempt.
- Defers the actual send via transaction.on_commit (never inside open atomic block).
- Tries Celery (fast-fail broker probe) then falls back to a daemon thread.
- Never blocks the web request thread.
- Never silently drops: every failure is recorded in the EmailLog row.
"""
import logging
import threading
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

# Staleness threshold for the retryability rule.
# A pending/retrying row older than this (since last_attempt_at or created) is
# considered stuck and can be retried by the admin.
EMAIL_LOG_STALE_AFTER = timedelta(minutes=5)


def email_log_is_retryable(email_log) -> bool:
    """Return True if this EmailLog row can be retried by the admin.

    Rules:
    - 'confirmed' rows: never retryable.
    - 'failed' rows: always retryable.
    - 'pending' or 'retrying' rows: retryable only if stale (no progress for
      longer than EMAIL_LOG_STALE_AFTER since last_attempt_at or created).
    """
    if email_log.status == 'confirmed':
        return False
    if email_log.status == 'failed':
        return True
    # pending or retrying — check staleness
    reference = email_log.last_attempt_at or email_log.created
    if reference is None:
        return True  # no reference point → treat as stale
    now = timezone.now()
    return (now - reference) > EMAIL_LOG_STALE_AFTER


def should_notify_admin_of_status_change(order, changed_by) -> bool:
    """Return True if the admin should receive a status-change notification.

    Decision matrix (ADR decision #3):
    - changed_by is None → system/IPN-driven → email admin.
    - changed_by is a non-staff user → customer-driven → email admin.
    - changed_by is staff/superuser + new_status in {cancelled, refunded} → always email admin.
    - changed_by is staff/superuser + other statuses → skip admin email.
    """
    new_status = order.status
    if new_status in ('cancelled', 'refunded'):
        return True
    if changed_by is None:
        return True
    if not changed_by.is_staff:
        return True
    return False


def _create_email_log(
    *,
    email_type: str,
    task_name: str,
    task_args: dict,
    template_name: str,
    subject: str,
    recipient_email: str,
    recipient_user=None,
    order_id: int | None = None,
) -> int | None:
    """Create a pending EmailLog row. Returns the pk or None on failure."""
    try:
        from orders.models import EmailLog, Order
        order = None
        if order_id is not None:
            try:
                order = Order.objects.get(pk=order_id)
            except Order.DoesNotExist:
                pass

        log = EmailLog.objects.create(
            email_type=email_type,
            task_name=task_name,
            task_args=task_args,
            template_name=template_name,
            subject=subject,
            recipient_email=recipient_email,
            recipient_user=recipient_user,
            order=order,
            status='pending',
        )
        return log.pk
    except Exception as exc:
        logger.error('dispatch_order_email: could not create EmailLog: %s', exc)
        return None


def _run_via_thread(task, args: tuple, kwargs: dict) -> None:
    """Run the task body on a daemon thread (fallback when Celery is unavailable)."""
    def _run():
        try:
            task.run(*args, **kwargs)
        except Exception as exc:
            logger.error(
                'dispatch_order_email: thread raised exception for task %s: %s',
                task.name, exc,
            )

    t = threading.Thread(target=_run, name='order-email', daemon=True)
    t.start()


def _run_via_celery(task, args: tuple, kwargs: dict) -> bool:
    """Attempt to dispatch via Celery. Returns True on success, False on failure."""
    try:
        task.apply_async(
            args=args,
            kwargs=kwargs,
            retry=False,
        )
        return True
    except Exception as exc:
        logger.warning(
            'dispatch_order_email: Celery broker unavailable for task %s (%s), '
            'falling back to thread.',
            task.name, exc,
        )
        return False


def dispatch_order_email(task, *args, order_id: int | None = None, email_type: str | None = None, **kwargs) -> None:
    """Dispatch an order email safely.

    1. Creates an EmailLog row (inside current transaction).
    2. Defers the actual send to transaction.on_commit.
    3. On commit: tries Celery (fast-fail), falls back to daemon thread.

    Parameters
    ----------
    task : Celery task object
        The Celery task to dispatch (e.g. send_payment_received_email).
    *args : positional args
        Passed through to the task.
    order_id : int or None
        Used to link the EmailLog to the Order.
    email_type : str or None
        An EmailLog.EmailType value (e.g. 'customer_payment_received').
    **kwargs : keyword args
        Passed through to the task.
    """
    from django.conf import settings

    # Derive metadata from the task name for the EmailLog row.
    # Tasks are expected to expose template_name / subject via their .name attribute
    # but we keep it simple: store the task name and pass email_log_id through kwargs.
    email_log_id: int | None = None

    if email_type:
        # Build a placeholder subject and template for the log row.
        # The actual subject/template are rendered inside the task body.
        # We store a lightweight stub so the log row has enough for display.
        placeholder_subject = _email_type_to_subject(email_type, order_id)
        placeholder_template = _email_type_to_template(email_type)

        recipient_email = _resolve_recipient_email(task, args, email_type)

        # recipient_user: try to resolve from the order
        recipient_user = _resolve_recipient_user(order_id, email_type)

        task_args_payload = {
            'args': list(args),
            'kwargs': {k: v for k, v in kwargs.items() if k != 'email_log_id'},
        }

        email_log_id = _create_email_log(
            email_type=email_type,
            task_name=task.name,
            task_args=task_args_payload,
            template_name=placeholder_template,
            subject=placeholder_subject,
            recipient_email=recipient_email,
            recipient_user=recipient_user,
            order_id=order_id,
        )

    # Thread the email_log_id into the task kwargs
    send_kwargs = dict(kwargs)
    if email_log_id is not None:
        send_kwargs['email_log_id'] = email_log_id

    send_args = args

    def _on_commit():
        use_celery = getattr(settings, 'USE_CELERY', True)
        celery_eager = getattr(settings, 'CELERY_TASK_ALWAYS_EAGER', False)

        dispatched = False
        if use_celery and not celery_eager:
            dispatched = _run_via_celery(task, send_args, send_kwargs)

        if not dispatched:
            _run_via_thread(task, send_args, send_kwargs)

    transaction.on_commit(_on_commit)


def retry_email_log(email_log) -> None:
    """Re-dispatch a failed or stale EmailLog row.

    Reuses the existing row (no new row created). Resolves the task from the
    Celery registry by task_name and re-runs dispatch logic inline (on_commit
    runs immediately when no active transaction).
    """
    from django.conf import settings
    from celery import current_app

    # Resolve the task object from the registry
    task_name = email_log.task_name
    try:
        task = current_app.tasks[task_name]
    except KeyError:
        from orders.models import EmailLog
        logger.error(
            'retry_email_log: task "%s" not found in Celery registry. '
            'The task may have been renamed or removed.',
            task_name,
        )
        EmailLog.objects.filter(pk=email_log.pk).update(
            status='failed',
            error_message=f'Task "{task_name}" not found in registry — may have been renamed.',
            last_attempt_at=timezone.now(),
        )
        return

    # Reset to pending
    from orders.models import EmailLog
    EmailLog.objects.filter(pk=email_log.pk).update(
        status='pending',
        error_message='',
    )

    # Build args/kwargs from stored payload
    task_args_payload = email_log.task_args or {}
    send_args = tuple(task_args_payload.get('args', []))
    send_kwargs = dict(task_args_payload.get('kwargs', {}))
    send_kwargs['email_log_id'] = email_log.pk

    use_celery = getattr(settings, 'USE_CELERY', True)
    celery_eager = getattr(settings, 'CELERY_TASK_ALWAYS_EAGER', False)

    dispatched = False
    if use_celery and not celery_eager:
        dispatched = _run_via_celery(task, send_args, send_kwargs)

    if not dispatched:
        _run_via_thread(task, send_args, send_kwargs)


# ---------------------------------------------------------------------------
# Private helpers for metadata derivation
# ---------------------------------------------------------------------------

_EMAIL_TYPE_TEMPLATES = {
    'customer_payment_received': 'orders/payment_received.html',
    'customer_status_update': 'orders/order_status_update.html',
    'customer_refund': 'orders/refund_notification.html',
    'admin_new_paid_order': 'orders/admin/new_paid_order.html',
    'admin_status_update': 'orders/admin/order_status_update.html',
    'admin_amount_mismatch': 'orders/admin/amount_mismatch.html',
}

_EMAIL_TYPE_SUBJECTS = {
    'customer_payment_received': 'Pago confirmado — Pedido',
    'customer_status_update': 'Actualización de tu pedido',
    'customer_refund': 'Reembolso procesado — Pedido',
    'admin_new_paid_order': '[Pedido pagado]',
    'admin_status_update': '[Actualización de pedido]',
    'admin_amount_mismatch': '[ALERTA] Monto incorrecto — Pedido',
}


def _email_type_to_template(email_type: str) -> str:
    return _EMAIL_TYPE_TEMPLATES.get(email_type, '')


def _email_type_to_subject(email_type: str, order_id: int | None) -> str:
    base = _EMAIL_TYPE_SUBJECTS.get(email_type, email_type)
    if order_id:
        return f'{base} #{order_id}'
    return base


def _resolve_recipient_email(task, args: tuple, email_type: str) -> str:
    """Best-effort resolution of the recipient email from task args."""
    # For customer emails: args[0] is order_id
    if email_type.startswith('customer_') and args:
        try:
            from orders.models import Order
            order = Order.objects.select_related('user').get(pk=args[0])
            return order.email or (order.user.email if order.user else '')
        except Exception:
            pass
    # For admin emails: resolve admin email
    if email_type.startswith('admin_'):
        from orders.email_utils import resolve_admin_email
        return resolve_admin_email() or ''
    return ''


def _resolve_recipient_user(order_id: int | None, email_type: str):
    """Best-effort resolution of the recipient User FK for customer emails."""
    if not email_type.startswith('customer_') or order_id is None:
        return None
    try:
        from orders.models import Order
        order = Order.objects.select_related('user').get(pk=order_id)
        return order.user
    except Exception:
        return None
