import logging

from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger(__name__)


@shared_task
def send_order_confirmation_email(order_id):
    """
    Send order confirmation email to the customer.
    Uses templates when available, falls back to logging.
    """
    from orders.models import Order

    try:
        order = Order.objects.select_related('user').get(pk=order_id)
    except Order.DoesNotExist:
        logger.error(f'Order {order_id} not found for confirmation email.')
        return

    recipient = order.email or order.user.email
    if not recipient:
        logger.warning(f'No email address for order {order.order_number}.')
        return

    subject = f'Order Confirmation - #{order.order_number}'

    try:
        from django.template import loader
        message = loader.get_template(
            'orders/order_confirmation.html'
        ).render({
            'order': order,
            'items': order.items.all(),
        })
        send_mail(
            subject=subject,
            message='',
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[recipient],
            html_message=message,
            fail_silently=False,
        )
        logger.info(f'Order confirmation email sent for order {order.order_number}.')
    except Exception as e:
        logger.warning(
            f'Could not send order confirmation email for order '
            f'{order.order_number}: {e}. Template may not exist yet.'
        )


@shared_task
def send_order_status_update_email(order_id):
    """
    Send order status update email to the customer.
    Uses templates when available, falls back to logging.
    """
    from orders.models import Order

    try:
        order = Order.objects.select_related('user').get(pk=order_id)
    except Order.DoesNotExist:
        logger.error(f'Order {order_id} not found for status update email.')
        return

    recipient = order.email or order.user.email
    if not recipient:
        logger.warning(f'No email address for order {order.order_number}.')
        return

    subject = f'Order Update - #{order.order_number}'

    try:
        from django.template import loader
        latest_history = order.status_history.order_by('-created').first()
        message = loader.get_template(
            'orders/order_status_update.html'
        ).render({
            'order': order,
            'new_status': order.get_status_display(),
            'note': latest_history.note if latest_history else '',
        })
        send_mail(
            subject=subject,
            message='',
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[recipient],
            html_message=message,
            fail_silently=False,
        )
        logger.info(f'Status update email sent for order {order.order_number}.')
    except Exception as e:
        logger.warning(
            f'Could not send status update email for order '
            f'{order.order_number}: {e}. Template may not exist yet.'
        )


# ADR-preferred alias
send_order_confirmation = send_order_confirmation_email


@shared_task
def send_order_status_changed(order_id, old_status, new_status):
    """Status-changed email with explicit old/new status context.

    Wired from OrderStateMachine.transition().
    """
    from orders.models import Order

    try:
        order = Order.objects.select_related('user').get(pk=order_id)
    except Order.DoesNotExist:
        logger.error('Order %s not found for status changed email.', order_id)
        return

    recipient = order.email or order.user.email
    if not recipient:
        logger.warning('No email address for order %s.', order.order_number)
        return

    subject = f'Tu pedido #{order.order_number} cambió a {new_status}'

    try:
        from django.template import loader
        message = loader.get_template('orders/order_status_changed.html').render({
            'order': order,
            'new_status': new_status,
            'old_status': old_status,
            'note': '',
        })
        send_mail(
            subject=subject,
            message='',
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[recipient],
            html_message=message,
            fail_silently=False,
        )
        logger.info('Status changed email sent for order %s (%s→%s).', order.order_number, old_status, new_status)
    except Exception as exc:
        logger.warning(
            'Could not send status changed email for order %s: %s',
            order.order_number, exc,
        )


@shared_task
def send_payment_received_email(order_id):
    """Send payment received / order confirmed notification to the customer.

    Queued by the IPN PAID handler (ADR §4, task item 10).
    """
    from orders.models import Order

    try:
        order = Order.objects.select_related('user').get(pk=order_id)
    except Order.DoesNotExist:
        logger.error('Order %s not found for payment received email.', order_id)
        return

    recipient = order.email or order.user.email
    if not recipient:
        logger.warning('No email address for order %s.', order.order_number)
        return

    subject = f'Pago recibido - Pedido #{order.order_number}'

    try:
        from django.template import loader
        message = loader.get_template('orders/payment_received.html').render({
            'order': order,
            'items': order.items.all(),
        })
        send_mail(
            subject=subject,
            message='',
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[recipient],
            html_message=message,
            fail_silently=False,
        )
        logger.info('Payment received email sent for order %s.', order.order_number)
    except Exception as exc:
        logger.warning(
            'Could not send payment received email for order %s: %s. '
            'Template may not exist yet.',
            order.order_number, exc,
        )


@shared_task
def notify_admin_payment_received(order_id):
    """Send an internal admin notification when a payment is received.

    ADR §4 task item 10, wired into IPN PAID flow.
    """
    from orders.models import Order

    try:
        order = Order.objects.select_related('user').get(pk=order_id)
    except Order.DoesNotExist:
        logger.error('Order %s not found for admin payment notification.', order_id)
        return

    admin_email = getattr(settings, 'ADMIN_USER', None) or getattr(
        settings, 'DEFAULT_FROM_EMAIL', None
    )
    if not admin_email:
        logger.warning('No admin email configured for payment notification.')
        return

    subject = f'[Admin] Pago recibido — Pedido #{order.order_number}'
    message = (
        f'Se recibió el pago para el pedido {order.order_number}.\n'
        f'Cliente: {order.user.email}\n'
        f'Total: S/ {order.total}\n'
        f'Método: {order.payment_method}\n'
        f'Transaction ID: {order.izipay_transaction_id}\n'
    )

    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[admin_email],
            fail_silently=False,
        )
        logger.info('Admin payment notification sent for order %s.', order.order_number)
    except Exception as exc:
        logger.warning(
            'Could not send admin payment notification for order %s: %s',
            order.order_number, exc,
        )


@shared_task
def send_admin_amount_mismatch_alert(order_id, expected_centimos, received_centimos):
    """Alert admin when the IPN payment amount does not match the order total.

    ADR BP4 — queued when amount mismatch is detected.
    """
    from orders.models import Order

    try:
        order = Order.objects.select_related('user').get(pk=order_id)
    except Order.DoesNotExist:
        logger.error('Order %s not found for amount mismatch alert.', order_id)
        return

    admin_email = getattr(settings, 'ADMIN_USER', None) or getattr(
        settings, 'DEFAULT_FROM_EMAIL', None
    )
    if not admin_email:
        logger.warning('No admin email configured for amount mismatch alert.')
        return

    subject = f'[ALERTA] Monto incorrecto — Pedido #{order.order_number}'
    message = (
        f'ALERTA: El IPN de Izipay reportó un monto distinto al esperado.\n\n'
        f'Pedido: {order.order_number}\n'
        f'Cliente: {order.user.email}\n'
        f'Monto esperado: {expected_centimos} céntimos (S/ {expected_centimos / 100:.2f})\n'
        f'Monto recibido: {received_centimos} céntimos (S/ {received_centimos / 100:.2f})\n\n'
        f'El pedido permanece sin pagar. Revisa en el back-office de Izipay.'
    )

    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[admin_email],
            fail_silently=False,
        )
        logger.info('Amount mismatch alert sent for order %s.', order.order_number)
    except Exception as exc:
        logger.warning(
            'Could not send amount mismatch alert for order %s: %s',
            order.order_number, exc,
        )


@shared_task
def clear_cart_on_payment(user_id):
    """Clear a user's cart after payment is confirmed.

    ADR D5 — can be called as a standalone task if needed.
    Note: In the IPN handler, cart is cleared directly inside the atomic block.
    This task is available for deferred or retry scenarios.
    """
    from django.contrib.auth import get_user_model
    from orders.models import Cart

    User = get_user_model()
    try:
        user = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        logger.error('User %s not found for cart clear.', user_id)
        return

    cart = Cart.objects.filter(user=user).first()
    if cart:
        deleted_count, _ = cart.items.all().delete()
        logger.info('Cleared %d cart items for user %s.', deleted_count, user_id)
    else:
        logger.info('No cart found for user %s.', user_id)


@shared_task
def send_refund_email(order_id):
    """Send refund/cancellation notification to the customer.

    Queued by the IPN REFUNDED/CANCELLED handler.
    """
    from orders.models import Order

    try:
        order = Order.objects.select_related('user').get(pk=order_id)
    except Order.DoesNotExist:
        logger.error('Order %s not found for refund email.', order_id)
        return

    recipient = order.email or order.user.email
    if not recipient:
        logger.warning('No email address for order %s.', order.order_number)
        return

    subject = f'Reembolso procesado - Pedido #{order.order_number}'

    try:
        from django.template import loader
        message = loader.get_template('orders/refund_notification.html').render({
            'order': order,
        })
        send_mail(
            subject=subject,
            message='',
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[recipient],
            html_message=message,
            fail_silently=False,
        )
        logger.info('Refund email sent for order %s.', order.order_number)
    except Exception as exc:
        logger.warning(
            'Could not send refund email for order %s: %s. '
            'Template may not exist yet.',
            order.order_number, exc,
        )
