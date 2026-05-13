"""
Data migration: seed canonical ConfiguracionTienda keys.
Calls the seed_site_config management command logic directly (idempotent).
"""

from django.db import migrations

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


def seed_site_config(apps, schema_editor):
    ConfiguracionTienda = apps.get_model('marketing', 'ConfiguracionTienda')
    for entry in SEED_DATA:
        ConfiguracionTienda.objects.update_or_create(
            clave=entry['clave'],
            defaults={
                'valor': entry['valor'],
                'descripcion': entry['descripcion'],
            },
        )


def reverse_seed(apps, schema_editor):
    # Intentionally a no-op: we do not delete config keys on rollback
    # because an operator may have modified values after migration ran.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('marketing', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(seed_site_config, reverse_code=reverse_seed),
    ]
