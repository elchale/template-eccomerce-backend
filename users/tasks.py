import logging
from celery import shared_task
from django.db.models import Model
from django.conf import settings
from django.core.mail import send_mail
from django.template import loader
from django.utils import timezone
from django.utils.translation import gettext as _
from django.contrib.auth import get_user_model

logger = logging.getLogger(__name__)

User: Model = get_user_model()

@shared_task
def notify_user_duplicate_registration(username, ip, browser, os):
    """
    Send email to user that there was an attempt to register an account with his email
    """
    now = timezone.now()
    params = {
        'username': username,
        'ip_address': ip,
        'browser': browser,
        'os': os,
        'time': now
    }
    subject = loader.get_template('accounts/duplicate_account_registration.txt').render()
    message = loader.get_template('accounts/duplicate_account_registration.html').render(context=params)

    send_mail(
        subject=subject,
        message='',
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[username],
        html_message=message,
        fail_silently=False
    )



@shared_task
def notify_user_ip_changed(user_id, ip, device, os, browser):
    """
    Send email to user that there was an attempt to login from a new ip address
    """
    now = timezone.now()
    user = User.objects.filter(pk=user_id).first()

    params = {
        'username': user.username,
        'ip_address': ip,
        'device': device,
        'os': os,
        'browser': browser,
        'time': now
    }

    msg = loader.get_template('accounts/ip_changed.html').render(params).strip()
    subject = _('Nuevo inicio de sesión')
    send_mail(
        subject,
        '',
        settings.DEFAULT_FROM_EMAIL,
        [user.email],
        html_message=msg,
        fail_silently=False
    )



@shared_task
def notify_failed_login(user_id):
    """
    Send email to user that there was an attempt to login with incorrect password
    """
    user = get_user_model().objects.filter(pk=user_id).first()

    params = {
        'username': user.username,
    }

    msg = loader.get_template('accounts/failed_login.html').render(params).strip()
    subject = _('Login fallido')
    send_mail(
        subject,
        '',
        settings.DEFAULT_FROM_EMAIL,
        [user.email],
        html_message=msg,
        fail_silently=False
    )


@shared_task
def send_password_change_notification(user_id):
    """Notify the user that their password was changed successfully.

    Enqueued from PasswdChangeSerializer.save() so the email goes out
    asynchronously after the password is already persisted.
    """
    user = User.objects.filter(pk=user_id).first()
    if not user:
        logger.warning('send_password_change_notification: user %s not found', user_id)
        return

    brand = getattr(settings, 'BRAND', getattr(settings, 'PROJECT_NAME', 'Qolca'))

    try:
        html_msg = loader.get_template('accounts/password_changed.html').render({
            'user': user,
            'brand': brand,
        })
        txt_msg = loader.get_template('accounts/password_changed.txt').render({
            'user': user,
            'brand': brand,
        })
        subject = f'Cambiaste tu contraseña en {brand}'
        send_mail(
            subject,
            txt_msg,
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
            html_message=html_msg,
            fail_silently=False,
        )
        logger.info('Password change notification sent to %s', user.email)
    except Exception as exc:
        logger.warning(
            'Could not send password change notification to %s: %s',
            user.email, exc,
        )
