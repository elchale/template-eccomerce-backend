"""Shared email send helper for all order email tasks.

Responsibilities:
- Build multipart EmailMultiAlternatives (HTML + .txt sibling).
- Open SMTP with a bounded socket timeout (EMAIL_TIMEOUT setting).
- Retry up to MAX_SEND_ATTEMPTS on transient SMTPException / socket.timeout.
- Update the bound EmailLog row on every attempt, and on final success/failure.
- Validate the admin recipient email; fall back to DEFAULT_FROM_EMAIL when invalid.

This module is imported by tasks.py; it never imports from tasks.py (no circular).
"""
import logging
import smtplib
import socket
import time

from django.conf import settings
from django.core.mail import EmailMultiAlternatives, get_connection
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.template import TemplateDoesNotExist
from django.template.loader import get_template
from django.utils import timezone

logger = logging.getLogger(__name__)

# Bounded retry config (not env vars — internal constants)
MAX_SEND_ATTEMPTS = 3
RETRY_DELAYS = (1, 2)  # seconds between attempt 1→2 and 2→3


def _get_email_timeout() -> int:
    """Return the configured SMTP socket timeout in seconds."""
    return int(getattr(settings, 'EMAIL_TIMEOUT', 10))


def resolve_admin_email() -> str | None:
    """Return a validated admin email address.

    Tries ADMIN_USER first, then DEFAULT_FROM_EMAIL. If both fail validation,
    logs an ERROR and returns None (caller should skip the admin send).
    """
    candidates = [
        getattr(settings, 'ADMIN_USER', None),
        getattr(settings, 'DEFAULT_FROM_EMAIL', None),
    ]
    for candidate in candidates:
        if not candidate:
            continue
        try:
            validate_email(candidate)
            return candidate
        except ValidationError:
            logger.warning('EmailUtils: admin email candidate "%s" is not a valid email address.', candidate)
    logger.error(
        'EmailUtils: no valid admin email found in ADMIN_USER or DEFAULT_FROM_EMAIL. '
        'Admin email send skipped.'
    )
    return None


def _update_email_log(email_log_id: int | None, **fields) -> None:
    """Update EmailLog fields by pk without a full model load."""
    if email_log_id is None:
        return
    try:
        from orders.models import EmailLog
        EmailLog.objects.filter(pk=email_log_id).update(**fields)
    except Exception as exc:
        logger.warning('EmailUtils: could not update EmailLog %s: %s', email_log_id, exc)


def send_order_email(
    *,
    template_html: str,
    template_txt: str,
    context: dict,
    subject: str,
    recipient: str,
    email_log_id: int | None = None,
) -> bool:
    """Render and send a multipart order email with bounded retry.

    Parameters
    ----------
    template_html : str
        Django template path for the HTML part.
    template_txt : str
        Django template path for the plain-text part (sibling .txt file).
    context : dict
        Template render context.
    subject : str
        Email subject line.
    recipient : str
        Recipient email address.
    email_log_id : int or None
        If provided, the EmailLog row is updated on each attempt and on
        final success/failure.

    Returns
    -------
    bool
        True if the email was sent successfully; False after all retries
        exhausted.
    """
    # Render templates
    try:
        html_body = get_template(template_html).render(context)
    except TemplateDoesNotExist as exc:
        error_msg = f'HTML template not found: {template_html} — {exc}'
        logger.error('EmailUtils: %s', error_msg)
        _update_email_log(
            email_log_id,
            status='failed',
            error_message=error_msg,
            last_attempt_at=timezone.now(),
        )
        return False
    except Exception as exc:
        error_msg = f'HTML template render error: {exc}'
        logger.error('EmailUtils: %s (template=%s)', error_msg, template_html)
        _update_email_log(
            email_log_id,
            status='failed',
            error_message=error_msg,
            last_attempt_at=timezone.now(),
        )
        return False

    try:
        txt_body = get_template(template_txt).render(context)
    except TemplateDoesNotExist:
        txt_body = ''  # .txt sibling is optional
    except Exception as exc:
        logger.warning('EmailUtils: txt template render error: %s (template=%s)', exc, template_txt)
        txt_body = ''

    timeout = _get_email_timeout()
    last_error = ''

    for attempt in range(1, MAX_SEND_ATTEMPTS + 1):
        now = timezone.now()
        # Update log: increment attempts, set last_attempt_at, mark retrying when >1st attempt
        if email_log_id is not None:
            update_fields = {
                'attempts': attempt,
                'last_attempt_at': now,
            }
            if attempt > 1:
                update_fields['status'] = 'retrying'
            _update_email_log(email_log_id, **update_fields)

        try:
            connection = get_connection(
                timeout=timeout,
                fail_silently=False,
            )
            msg = EmailMultiAlternatives(
                subject=subject,
                body=txt_body or ' ',
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[recipient],
                connection=connection,
            )
            msg.attach_alternative(html_body, 'text/html')
            msg.send()

            # Success
            _update_email_log(
                email_log_id,
                status='confirmed',
                sent_at=timezone.now(),
                last_attempt_at=timezone.now(),
            )
            logger.info(
                'EmailUtils: sent "%s" to %s (attempt %d)',
                subject[:60], recipient, attempt,
            )
            return True

        except (smtplib.SMTPException, socket.timeout, OSError, ConnectionError) as exc:
            last_error = str(exc)
            logger.warning(
                'EmailUtils: transient send failure (attempt %d/%d) for "%s" to %s: %s',
                attempt, MAX_SEND_ATTEMPTS, subject[:60], recipient, exc,
            )
            if attempt < MAX_SEND_ATTEMPTS:
                sleep_secs = RETRY_DELAYS[attempt - 1] if attempt - 1 < len(RETRY_DELAYS) else RETRY_DELAYS[-1]
                time.sleep(sleep_secs)

        except Exception as exc:
            # Non-transient error — do not retry
            last_error = str(exc)
            logger.error(
                'EmailUtils: non-transient send failure for "%s" to %s: %s',
                subject[:60], recipient, exc,
            )
            break

    # All attempts exhausted
    _update_email_log(
        email_log_id,
        status='failed',
        error_message=last_error,
        last_attempt_at=timezone.now(),
    )
    logger.error(
        'EmailUtils: gave up sending "%s" to %s after %d attempts. Last error: %s',
        subject[:60], recipient, MAX_SEND_ATTEMPTS, last_error,
    )
    return False
