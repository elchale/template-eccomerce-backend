"""
Management command: setup_google_oauth

Creates (or updates) the allauth SocialApp record for Google OAuth and
attaches it to the default Site.

Usage:
    python manage.py setup_google_oauth

Run once after the initial migrate, or re-run idempotently at any time.
The CLIENT_ID and SECRET are read from environment variables so that this
command is safe to run in CI / deployment pipelines without hard-coding
credentials.
"""
from django.core.management.base import BaseCommand
from django.conf import settings


class Command(BaseCommand):
    help = 'Create or update the Google OAuth SocialApp record in the database.'

    def handle(self, *args, **options):
        # Import here to avoid AppRegistryNotReady errors at module load time.
        from allauth.socialaccount.models import SocialApp
        from django.contrib.sites.models import Site

        client_id = getattr(settings, 'GOOGLE_OAUTH_CLIENT_ID', '')
        secret = getattr(settings, 'GOOGLE_OAUTH_CLIENT_SECRET', '')

        if not client_id or not secret:
            self.stderr.write(
                self.style.ERROR(
                    'GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET must be '
                    'set in the environment / settings before running this command.'
                )
            )
            return

        app, created = SocialApp.objects.update_or_create(
            provider='google',
            defaults={
                'name': 'Google',
                'client_id': client_id,
                'secret': secret,
            },
        )

        site = Site.objects.get_current()
        app.sites.add(site)

        verb = 'Created' if created else 'Updated'
        self.stdout.write(
            self.style.SUCCESS(
                f"{verb} Google SocialApp (id={app.pk}) and linked to site "
                f"'{site.domain}' (id={site.pk})."
            )
        )
