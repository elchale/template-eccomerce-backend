"""Order lifecycle email tasks.

Each task accepts an optional `email_log_id` kwarg so email_utils can update
the corresponding EmailLog row on success/failure.

Tasks removed in this version (ADR decision #1):
- send_order_confirmation_email (at-checkout confirmation — deleted call site)
- send_order_status_update_email (dead — superseded by send_order_status_changed)
- send_order_confirmation (alias)

Tasks kept / updated:
- send_payment_received_email   — customer payment confirmed (IPN PAID)
- notify_admin_payment_received — admin new paid order (IPN PAID)
- send_admin_amount_mismatch_alert — admin amount mismatch alert (IPN bad amount)
- send_order_status_changed     — customer + optional admin status update
- send_refund_email             — customer refund/cancellation notification
- clear_cart_on_payment         — clear cart after payment (utility)
"""
import logging

from celery import shared_task
from django.conf import settings

from orders.email_utils import resolve_admin_email, send_order_email

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Customer: payment received / order confirmed
# ---------------------------------------------------------------------------

@shared_task
def send_payment_received_email(order_id, *, email_log_id=None):
    """Send payment received / order confirmed notification to the customer.

    Template: orders/payment_received.html + .txt
    Triggered by IPN PAID handler via dispatch_order_email.
    """
    from orders.models import Order

    try:
        order = Order.objects.select_related('user').prefetch_related('items').get(pk=order_id)
    except Order.DoesNotExist:
        logger.error('send_payment_received_email: Order %s not found.', order_id)
        return

    recipient = order.email or (order.user.email if order.user else None)
    if not recipient:
        logger.warning(
            'send_payment_received_email: No email address for order %s.',
            order.order_number,
        )
        return

    subject = f'Pago confirmado — Pedido #{order.order_number}'
    context = {
        'order': order,
        'items': order.items.all(),
    }

    send_order_email(
        template_html='orders/payment_received.html',
        template_txt='orders/payment_received.txt',
        context=context,
        subject=subject,
        recipient=recipient,
        email_log_id=email_log_id,
    )


# ---------------------------------------------------------------------------
# Admin: new paid order
# ---------------------------------------------------------------------------

@shared_task
def notify_admin_payment_received(order_id, *, email_log_id=None):
    """Send admin notification when a payment is received.

    Template: orders/admin/new_paid_order.html + .txt
    Triggered by IPN PAID handler via dispatch_order_email.
    """
    from orders.models import Order

    try:
        order = Order.objects.select_related('user').prefetch_related('items').get(pk=order_id)
    except Order.DoesNotExist:
        logger.error('notify_admin_payment_received: Order %s not found.', order_id)
        return

    admin_email = resolve_admin_email()
    if not admin_email:
        return

    frontend_domain = getattr(settings, 'FRONTEND_DOMAIN', getattr(settings, 'DOMAIN', ''))
    admin_order_url = f'https://{frontend_domain}/admin/orders/{order.pk}' if frontend_domain else ''

    subject = f'[Pedido pagado] #{order.order_number} — {order.currency_code} {order.total}'
    context = {
        'order': order,
        'items': order.items.all(),
        'admin_order_url': admin_order_url,
    }

    send_order_email(
        template_html='orders/admin/new_paid_order.html',
        template_txt='orders/admin/new_paid_order.txt',
        context=context,
        subject=subject,
        recipient=admin_email,
        email_log_id=email_log_id,
    )


# ---------------------------------------------------------------------------
# Admin: amount mismatch alert
# ---------------------------------------------------------------------------

@shared_task
def send_admin_amount_mismatch_alert(order_id, expected_centimos, received_centimos, *, email_log_id=None):
    """Alert admin when the IPN payment amount does not match the order total.

    Template: orders/admin/amount_mismatch.html + .txt
    Triggered by IPN bad-amount check via dispatch_order_email.
    """
    from orders.models import Order

    try:
        order = Order.objects.select_related('user').get(pk=order_id)
    except Order.DoesNotExist:
        logger.error('send_admin_amount_mismatch_alert: Order %s not found.', order_id)
        return

    admin_email = resolve_admin_email()
    if not admin_email:
        return

    frontend_domain = getattr(settings, 'FRONTEND_DOMAIN', getattr(settings, 'DOMAIN', ''))
    admin_order_url = f'https://{frontend_domain}/admin/orders/{order.pk}' if frontend_domain else ''

    subject = f'[ALERTA] Monto incorrecto — Pedido #{order.order_number}'
    context = {
        'order': order,
        'expected_centimos': expected_centimos,
        'received_centimos': received_centimos,
        'expected_soles': expected_centimos / 100,
        'received_soles': received_centimos / 100,
        'admin_order_url': admin_order_url,
    }

    send_order_email(
        template_html='orders/admin/amount_mismatch.html',
        template_txt='orders/admin/amount_mismatch.txt',
        context=context,
        subject=subject,
        recipient=admin_email,
        email_log_id=email_log_id,
    )


# ---------------------------------------------------------------------------
# Customer + optional admin: order status changed
# ---------------------------------------------------------------------------

@shared_task
def send_order_status_changed(order_id, old_status, new_status, *, changed_by_id=None, email_log_id=None):
    """Send customer (and optionally admin) notification on order status change.

    Template (customer): orders/order_status_update.html + .txt
    Template (admin):    orders/admin/order_status_update.html + .txt

    The admin branch is governed by should_notify_admin_of_status_change().
    changed_by_id is the User.pk who triggered the change (None = system/IPN).
    """
    from django.contrib.auth import get_user_model
    from orders.models import Order
    from orders.email_dispatch import should_notify_admin_of_status_change

    User = get_user_model()

    try:
        order = Order.objects.select_related('user').get(pk=order_id)
    except Order.DoesNotExist:
        logger.error('send_order_status_changed: Order %s not found.', order_id)
        return

    # Resolve changed_by user for the admin-notify rule
    changed_by = None
    if changed_by_id is not None:
        try:
            changed_by = User.objects.get(pk=changed_by_id)
        except User.DoesNotExist:
            logger.warning(
                'send_order_status_changed: User %s not found for changed_by.', changed_by_id
            )

    # Resolve human-readable status labels
    status_display_map = dict(Order.Status.choices)
    old_status_display = status_display_map.get(old_status, old_status)
    new_status_display = status_display_map.get(new_status, new_status)

    # Fetch the latest history note for context
    latest_history = order.status_history.order_by('-created').first()
    note = latest_history.note if latest_history else ''

    # --- Customer email ---
    recipient = order.email or (order.user.email if order.user else None)
    if recipient:
        subject = f'Tu pedido #{order.order_number} ahora está {new_status_display}'
        customer_context = {
            'order': order,
            'old_status': old_status,
            'new_status': new_status,
            'old_status_display': old_status_display,
            'new_status_display': new_status_display,
            'note': note,
        }
        send_order_email(
            template_html='orders/order_status_update.html',
            template_txt='orders/order_status_update.txt',
            context=customer_context,
            subject=subject,
            recipient=recipient,
            email_log_id=email_log_id,  # Customer email uses the primary log row
        )
    else:
        logger.warning(
            'send_order_status_changed: No email address for order %s.', order.order_number
        )

    # --- Admin email (conditional) ---
    # Temporarily set the order status to new_status for the rule evaluation
    order.status = new_status
    if should_notify_admin_of_status_change(order, changed_by):
        admin_email = resolve_admin_email()
        if admin_email:
            frontend_domain = getattr(settings, 'FRONTEND_DOMAIN', getattr(settings, 'DOMAIN', ''))
            admin_order_url = f'https://{frontend_domain}/admin/orders/{order.pk}' if frontend_domain else ''
            changed_by_display = changed_by.email if changed_by else 'Sistema/IPN'

            admin_subject = f'[Pedido #{order.order_number}] {old_status_display} → {new_status_display}'
            admin_context = {
                'order': order,
                'old_status': old_status,
                'new_status': new_status,
                'old_status_display': old_status_display,
                'new_status_display': new_status_display,
                'note': note,
                'changed_by_display': changed_by_display,
                'admin_order_url': admin_order_url,
                'customer_email': recipient or '',
            }
            send_order_email(
                template_html='orders/admin/order_status_update.html',
                template_txt='orders/admin/order_status_update.txt',
                context=admin_context,
                subject=admin_subject,
                recipient=admin_email,
                email_log_id=None,  # Admin is a secondary send; no separate log here
            )


# ---------------------------------------------------------------------------
# Customer: refund / cancellation
# ---------------------------------------------------------------------------

@shared_task
def send_refund_email(order_id, *, email_log_id=None):
    """Send refund/cancellation notification to the customer.

    Template: orders/refund_notification.html + .txt
    Triggered by IPN REFUNDED/CANCELLED or admin refund via dispatch_order_email.
    """
    from orders.models import Order

    try:
        order = Order.objects.select_related('user').get(pk=order_id)
    except Order.DoesNotExist:
        logger.error('send_refund_email: Order %s not found.', order_id)
        return

    recipient = order.email or (order.user.email if order.user else None)
    if not recipient:
        logger.warning(
            'send_refund_email: No email address for order %s.', order.order_number
        )
        return

    subject = f'Reembolso procesado — Pedido #{order.order_number}'
    context = {
        'order': order,
    }

    send_order_email(
        template_html='orders/refund_notification.html',
        template_txt='orders/refund_notification.txt',
        context=context,
        subject=subject,
        recipient=recipient,
        email_log_id=email_log_id,
    )


# ---------------------------------------------------------------------------
# Utility: clear cart on payment
# ---------------------------------------------------------------------------

@shared_task
def clear_cart_on_payment(user_id):
    """Clear a user's cart after payment is confirmed.

    Note: In the IPN handler, cart is cleared directly inside the atomic block.
    This task is available for deferred or retry scenarios.
    """
    from django.contrib.auth import get_user_model
    from orders.models import Cart

    User = get_user_model()
    try:
        user = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        logger.error('clear_cart_on_payment: User %s not found.', user_id)
        return

    cart = Cart.objects.filter(user=user).first()
    if cart:
        deleted_count, _ = cart.items.all().delete()
        logger.info('clear_cart_on_payment: Cleared %d cart items for user %s.', deleted_count, user_id)
    else:
        logger.info('clear_cart_on_payment: No cart found for user %s.', user_id)
