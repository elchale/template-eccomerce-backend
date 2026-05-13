"""
Management command: seed_site_config

Idempotently seeds canonical ConfiguracionTienda keys.
Safe to run multiple times — uses update_or_create per key so existing
values are not overwritten if an operator has already customised them.

Usage:
    python manage.py seed_site_config
"""

from django.core.management.base import BaseCommand

SEED_DATA = [
    {
        'clave': 'site_name',
        'valor': 'Qolca Solutions',
        'descripcion': 'Nombre de la tienda mostrado en el encabezado y títulos de página.',
    },
    {
        'clave': 'contact_email',
        'valor': 'info@qolca.org',
        'descripcion': 'Correo electrónico de contacto público (Footer, página Contáctanos).',
    },
    {
        'clave': 'contact_phone',
        'valor': '',
        'descripcion': 'Teléfono de contacto público (opcional).',
    },
    {
        'clave': 'contact_address',
        'valor': 'Lima, Perú',
        'descripcion': 'Dirección física o de operaciones mostrada en el footer.',
    },
    {
        'clave': 'social_facebook',
        'valor': 'https://www.facebook.com/profile.php?id=61559863243995',
        'descripcion': 'URL del perfil de Facebook.',
    },
    {
        'clave': 'social_instagram',
        'valor': 'https://www.instagram.com/qolca.peru/',
        'descripcion': 'URL del perfil de Instagram.',
    },
    {
        'clave': 'social_tiktok',
        'valor': 'https://www.tiktok.com/@qolca.peru',
        'descripcion': 'URL del perfil de TikTok.',
    },
    {
        'clave': 'social_linkedin',
        'valor': 'https://www.linkedin.com/in/qolca-solutions/',
        'descripcion': 'URL del perfil de LinkedIn.',
    },
    {
        'clave': 'social_website',
        'valor': 'https://qolca.org',
        'descripcion': 'URL del sitio web corporativo externo.',
    },
    {
        'clave': 'footer_tagline',
        'valor': 'Productos de calidad, seleccionados para ti.',
        'descripcion': 'Frase corta debajo del logo en el footer.',
    },
    {
        'clave': 'footer_byline',
        'valor': 'Hecho con dedicación por Qolca',
        'descripcion': 'Texto al pie del footer (créditos / byline).',
    },
    {
        'clave': 'meta_description',
        'valor': '',
        'descripcion': 'Meta descripción por defecto para SEO (etiqueta <meta name="description">).',
    },
    {
        'clave': 'meta_keywords',
        'valor': '',
        'descripcion': 'Meta keywords por defecto para SEO (separadas por coma).',
    },
    {
        'clave': 'og_image_url',
        'valor': '',
        'descripcion': 'URL de la imagen por defecto para Open Graph (compartir en redes sociales).',
    },
    {
        'clave': 'currency',
        'valor': 'PEN',
        'descripcion': 'Código ISO 4217 de la moneda principal (ej. PEN, USD).',
    },
    {
        'clave': 'free_shipping_threshold',
        'valor': '0',
        'descripcion': 'Monto mínimo de compra (en la moneda configurada) para envío gratuito. 0 = sin envío gratis.',
    },
]


class Command(BaseCommand):
    help = 'Seed canonical ConfiguracionTienda keys (idempotent — uses update_or_create).'

    def handle(self, *args, **options):
        from django.conf import settings
        from marketing.models import ConfiguracionTienda

        project_name = getattr(settings, 'PROJECT_NAME', 'Eccomerce')

        # Patch name-dependent entries before writing
        for entry in SEED_DATA:
            if entry['clave'] == 'site_name':
                entry['valor'] = project_name
            elif entry['clave'] == 'footer_byline':
                entry['valor'] = f'Hecho con dedicación por {project_name}'

        created_count = 0
        updated_count = 0

        for entry in SEED_DATA:
            obj, created = ConfiguracionTienda.objects.update_or_create(
                clave=entry['clave'],
                defaults={
                    'valor': entry['valor'],
                    'descripcion': entry['descripcion'],
                },
            )
            if created:
                created_count += 1
            else:
                updated_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f'seed_site_config complete: {created_count} created, {updated_count} already existed.'
            )
        )
