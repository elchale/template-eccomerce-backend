#!/usr/bin/env python3
"""Email Template Test Script

Renders and optionally sends all email templates with dummy data for testing.
Useful for verifying email templates render correctly before production.

Usage:
    # Dry run (render only, no emails sent)
    python scripts/email_test.py --dry-run

    # Send test emails
    python scripts/email_test.py --to your@email.com

    # Test specific templates
    python scripts/email_test.py --to your@email.com --only "password"

    # Use custom sender address
    python scripts/email_test.py --to test@example.com --from custom@example.com

Examples:
    # Preview all templates (safe, no emails sent)
    python scripts/email_test.py --dry-run

    # Send all templates to yourself
    python scripts/email_test.py -t your@email.com

    # Test only password-related templates
    python scripts/email_test.py -t your@email.com --only password

    # Test with custom sender and recipient
    python scripts/email_test.py -t recipient@example.com -f sender@example.com

Options:
    -t, --to EMAIL          Recipient email address for test sends (required unless --dry-run)
    -f, --from EMAIL        Sender email address (default: from settings)
    --dry-run               Render only (do not send emails)
    --only SUBSTRING        Filter templates by name substring
    -h, --help              Show this help message
"""
import os
import sys
import argparse
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')

import django

django.setup()

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import EmailMultiAlternatives
from django.template import TemplateDoesNotExist
from django.template.loader import get_template

from utils.text_output import header, info, success, warning, error, section_separator


@dataclass(frozen=True)
class TemplateTarget:
    template_name: str
    subject: str


def _repo_root() -> Path:
    return Path(getattr(settings, 'BASE_DIR', Path.cwd())).resolve()


def _discover_template_names() -> list[str]:
    """Discover known email templates inside core/templates.

    We keep this scoped to templates that represent emails (not the password reset confirm web page).
    """
    base_dir = _repo_root()
    templates_root = base_dir / 'core' / 'templates'

    candidates: set[str] = set()

    for rel_dir in (
        Path('account') / 'email',
        Path('accounts'),
        Path('orders'),
    ):
        folder = templates_root / rel_dir
        if not folder.exists():
            continue

        for path in folder.rglob('*.html'):
            rel = path.relative_to(templates_root).as_posix()
            candidates.add(rel)

    # Ensure base layout is renderable too.
    candidates.add('base_layout.html')

    return sorted(candidates)


def _build_dummy_context() -> dict:
    User = get_user_model()

    dummy_user = User(
        username='test@example.com',
        email='test@example.com',
        first_name='John',
        last_name='Doe',
    )

    current_site = SimpleNamespace(
        name=getattr(settings, 'PROJECT_NAME', 'Project'),
        domain=getattr(settings, 'DOMAIN', 'example.com')
    )

    # Minimal dummy order context for orders/payment_received.html and siblings.
    # Uses SimpleNamespace so no DB is required when running --dry-run.
    dummy_item = SimpleNamespace(
        product_name='Producto de prueba',
        variant_info='Talla M',
        quantity=2,
        price='49.90',
    )
    dummy_order = SimpleNamespace(
        order_number='QLCA-20260516-TEST',
        currency_code='PEN',
        subtotal='99.80',
        discount_amount='0.00',
        shipping_amount='0.00',
        total='99.80',
        shipping_address='Av. Test 123, Lima, Perú',
        email='test@example.com',
        user=dummy_user,
        payment_method='izipay',
        izipay_transaction_id='tx-test-uuid-preview',
        status='confirmed',
        get_status_display=lambda: 'Confirmed',
    )

    return {
        'user': dummy_user,
        'username': 'test@example.com',
        'user_name': 'John Doe',
        'device': 'Desktop',
        'os': 'Windows',
        'browser': 'Chrome',
        'ip_address': '203.0.113.42',
        'time': '2025-12-14 12:00:00',
        'key': 'abc123xyz789',
        'password_reset_url': f"https://{getattr(settings, 'DOMAIN', 'example.com')}/reset-password/abc123xyz789/",
        'app_url': f"https://{getattr(settings, 'DOMAIN', 'example.com')}/",
        'current_site': current_site,
        'DOMAIN': getattr(settings, 'DOMAIN', 'example.com'),
        'BRAND': getattr(settings, 'PROJECT_NAME', 'Project'),
        # Order email context
        'order': dummy_order,
        'items': [dummy_item],
        'old_status': 'confirmed',
        'new_status': 'shipped',
        'old_status_display': 'Confirmado',
        'new_status_display': 'Enviado',
        'note': 'Nota de prueba',
        'changed_by_display': 'Sistema/IPN',
        'customer_email': 'test@example.com',
        'admin_order_url': f"https://{getattr(settings, 'DOMAIN', 'example.com')}/admin/orders/1",
        'expected_centimos': 10000,
        'received_centimos': 9999,
        'expected_soles': 100.00,
        'received_soles': 99.99,
    }


def _render_template(template_name: str, context: dict) -> str:
    template = get_template(template_name)
    return template.render(context)


def _try_render_text_alternative(template_name: str, context: dict) -> str | None:
    # If there's a .txt sibling for this template, render it.
    if template_name.endswith('.html'):
        txt_name = template_name[:-5] + '.txt'
    else:
        txt_name = template_name + '.txt'

    try:
        template = get_template(txt_name)
    except TemplateDoesNotExist:
        return None

    return template.render(context)


def _send_email(to_email: str, from_email: str | None, subject: str, html_body: str, text_body: str | None) -> None:
    sender = from_email or getattr(settings, 'DEFAULT_FROM_EMAIL', None)
    msg = EmailMultiAlternatives(
        subject=subject,
        body=text_body or ' ',
        from_email=sender,
        to=[to_email],
    )
    msg.attach_alternative(html_body, 'text/html')
    msg.send()


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Render and optionally send all email templates with dummy data.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Preview all templates (safe, no emails sent)
  python scripts/email_test.py --dry-run

  # Send all templates to your email
  python scripts/email_test.py --to your@email.com

  # Test only password-related templates
  python scripts/email_test.py -t your@email.com --only password

  # Test with custom sender
  python scripts/email_test.py -t recipient@example.com -f sender@example.com
        """
    )
    parser.add_argument(
        '-t', '--to',
        dest='to_email',
        help='Recipient email address for test sends'
    )
    parser.add_argument(
        '-f', '--from',
        dest='from_email',
        help='Sender email address (default: from settings.DEFAULT_FROM_EMAIL)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Render only (do not send emails)'
    )
    parser.add_argument(
        '--only',
        dest='only',
        help='Substring filter for template names (case-insensitive)'
    )

    args = parser.parse_args()

    header('Email Template Test')
    info('Renders email templates with dummy context and optionally sends them.')
    section_separator()

    # Validate arguments
    if not args.dry_run and not args.to_email:
        error('Either --to EMAIL or --dry-run is required.')
        error('Use --dry-run to render without sending, or --to EMAIL to send test emails.')
        return 1

    context = _build_dummy_context()
    template_names = _discover_template_names()

    # Filter templates if requested
    if args.only:
        original_count = len(template_names)
        template_names = [t for t in template_names if args.only.lower() in t.lower()]
        info(f'Filter: "{args.only}" matched {len(template_names)}/{original_count} templates')

    if not template_names:
        warning('No templates found to render.')
        return 0

    header('Templates to test')
    for name in template_names:
        info(name)
    section_separator()

    if args.dry_run:
        info('Mode: DRY RUN (no emails will be sent)')
    else:
        info(f'Mode: LIVE (emails will be sent to {args.to_email})')
        if args.from_email:
            info(f'Sender: {args.from_email}')
    section_separator()

    failures: list[tuple[str, str]] = []

    for template_name in template_names:
        header(f'Rendering: {template_name}')
        try:
            html = _render_template(template_name, context)
            text_alt = _try_render_text_alternative(template_name, context)
        except Exception as exc:
            error(f'Render failed: {exc}')
            failures.append((template_name, str(exc)))
            section_separator()
            continue

        success('Render ok')
        info(f'HTML length: {len(html)}')
        if text_alt is not None:
            info(f'Text length: {len(text_alt)}')

        if not args.dry_run:
            subject = f"[Email Test] {template_name}"
            try:
                _send_email(args.to_email, args.from_email, subject, html, text_alt)
                success(f'Sent to {args.to_email}')
            except Exception as exc:
                error(f'Send failed: {exc}')
                failures.append((template_name, f'send: {exc}'))

        section_separator()

    if failures:
        header('Summary: failures')
        for name, reason in failures:
            error(f'{name} -> {reason}')
        return 1

    success('Email Template Test Complete')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print()  # New line after ^C
        warning('Cancelled by user.')
        sys.exit(130)
    except Exception as exc:
        error(f'Unexpected error: {exc}')
        sys.exit(1)
