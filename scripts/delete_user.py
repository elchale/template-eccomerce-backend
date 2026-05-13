#!/usr/bin/env python3
"""Delete User Script

Safely deletes a user and all related objects using Django's cascade deletion.
Includes dry-run mode and confirmation prompt for safety.

Usage:
    # Dry run (preview only, safe)
    python scripts/delete_user.py --email user@example.com

    # Actually delete with confirmation
    python scripts/delete_user.py --email user@example.com --no-dry-run

    # Delete without confirmation prompt (dangerous!)
    python scripts/delete_user.py --email user@example.com --no-dry-run --yes

Examples:
    # See what would be deleted
    python scripts/delete_user.py -e test@example.com

    # Delete user after seeing preview
    python scripts/delete_user.py -e test@example.com --no-dry-run

Options:
    -e, --email EMAIL       Email of user to delete (required)
    --dry-run              Preview deletion without executing (default)
    --no-dry-run           Actually perform the deletion
    -y, --yes              Skip confirmation prompt (use with caution)
    -h, --help             Show this help message
"""
import os
import sys
import argparse

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')

import django

django.setup()

from django.contrib.auth import get_user_model
from django.db.models.deletion import Collector
from django.db.transaction import atomic
from django.core.exceptions import ObjectDoesNotExist

from utils.text_output import header, info, success, warning, error, section_separator


User = get_user_model()


def _get_user_by_email(email: str):
    if not email:
        raise ValueError('Email must be provided')
    return User.objects.get(email=email)


def _collector_summary(collector: Collector) -> dict[str, int]:
    summary: dict[str, int] = {}
    for model, objects in collector.data.items():
        label = f'{model._meta.app_label}.{model._meta.model_name}'
        summary[label] = len(objects)
    return dict(sorted(summary.items(), key=lambda item: (-item[1], item[0])))


def main():
    parser = argparse.ArgumentParser(
        description='Safely delete a user and all related objects using Django cascade deletion.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Preview what would be deleted (safe)
  python scripts/delete_user.py --email user@example.com

  # Actually delete the user
  python scripts/delete_user.py --email user@example.com --no-dry-run

  # Delete without confirmation (dangerous!)
  python scripts/delete_user.py -e user@example.com --no-dry-run --yes
        """
    )
    parser.add_argument(
        '-e', '--email',
        required=True,
        help='Email address of the user to delete'
    )
    parser.add_argument(
        '--dry-run',
        dest='dry_run',
        action='store_true',
        default=True,
        help='Preview deletion without executing (default)'
    )
    parser.add_argument(
        '--no-dry-run',
        dest='dry_run',
        action='store_false',
        help='Actually perform the deletion'
    )
    parser.add_argument(
        '-y', '--yes',
        dest='skip_confirmation',
        action='store_true',
        help='Skip confirmation prompt (use with caution)'
    )

    args = parser.parse_args()

    header('Delete User Script')
    info('This will delete the user and all related objects collected by Django cascading rules.')
    info(f'Email: {args.email}')
    info(f'Mode: {"DRY RUN (preview only)" if args.dry_run else "LIVE DELETION"}')
    section_separator()

    # Get user
    try:
        user = _get_user_by_email(args.email)
    except ObjectDoesNotExist:
        error(f'User with email "{args.email}" does not exist.')
        return 1
    except ValueError as exc:
        error(str(exc))
        return 1

    info(f'User: id={user.pk} username={user.get_username()} email={getattr(user, "email", "")}')

    # Collect objects that would be deleted
    db_alias = user._state.db or 'default'
    collector = Collector(using=db_alias)
    collector.collect([user])

    summary = _collector_summary(collector)

    section_separator()
    header('Objects to be deleted')
    for label, count in summary.items():
        info(f'{label}: {count}')

    section_separator()

    # Dry run - just show what would happen
    if args.dry_run:
        success('Dry run complete. No data was deleted.')
        info('To actually delete, run with --no-dry-run')
        return 0

    # Live deletion - require confirmation unless --yes flag
    if not args.skip_confirmation:
        warning('This action is IRREVERSIBLE!')
        expected = f'DELETE {user.pk}'
        try:
            typed = input(f"Type '{expected}' to confirm: ").strip()
        except (KeyboardInterrupt, EOFError):
            print()  # New line after ^C
            warning('Cancelled by user.')
            return 0

        if typed != expected:
            warning('Confirmation did not match. Aborting.')
            return 0

    # Perform deletion
    try:
        with atomic(using=db_alias):
            deleted_count, deleted_by_model = collector.delete()
    except Exception as exc:
        error(f'Deletion failed: {exc}')
        return 1

    section_separator()
    success(f'Delete completed. Total deleted objects: {deleted_count}')
    # Sort by count (descending) then by model label
    for model_label, count in sorted(
        deleted_by_model.items(),
        key=lambda item: (-item[1], item[0]),
    ):
        info(f'{model_label}: {count}')

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
