"""
Data migration: seed the SiteTheme singleton (pk=1) with default values.
"""
from django.db import migrations


def seed_site_theme(apps, schema_editor):
    SiteTheme = apps.get_model('marketing', 'SiteTheme')
    SiteTheme.objects.get_or_create(
        pk=1,
        defaults={
            'theme_id': 'classic',
            'custom_colors': {},
        },
    )


def unseed_site_theme(apps, schema_editor):
    SiteTheme = apps.get_model('marketing', 'SiteTheme')
    SiteTheme.objects.filter(pk=1).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('marketing', '0005_sitetheme'),
    ]

    operations = [
        migrations.RunPython(seed_site_theme, unseed_site_theme),
    ]
