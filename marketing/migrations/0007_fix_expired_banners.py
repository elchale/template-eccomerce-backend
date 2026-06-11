"""One-time data migration: reset fecha_fin → NULL on all marketing
content so seeded banners / popups / promos never silently expire.
Also creates the seed banners if they don't exist yet."""

from django.db import migrations
from django.utils import timezone
from datetime import timedelta


BANNERS = [
    {
        'nombre': 'Hero principal',
        'tipo': 'hero',
        'titulo_es': 'Nueva colección de temporada',
        'subtitulo_es': 'Descubre piezas seleccionadas con descuentos hasta 40%',
        'texto_cta_es': 'Comprar ahora',
        'enlace_cta': '/search',
        'imagen_url': 'https://images.unsplash.com/photo-1490481651871-ab68de25d43d?w=1920&q=85',
        'imagen_movil_url': 'https://images.unsplash.com/photo-1490481651871-ab68de25d43d?w=900&q=85',
        'color_fondo': '#0f172a',
        'color_texto': '#ffffff',
        'posicion': 0,
    },
    {
        'nombre': 'Anuncio envío gratis',
        'tipo': 'anuncio',
        'titulo_es': 'Envío gratis en pedidos sobre S/ 200',
        'subtitulo_es': 'En todo el territorio nacional',
        'texto_cta_es': 'Ver más',
        'enlace_cta': '/search',
        'imagen_url': 'https://images.unsplash.com/photo-1586528116311-ad8dd3c8310d?w=1600&q=85',
        'imagen_movil_url': 'https://images.unsplash.com/photo-1586528116311-ad8dd3c8310d?w=800&q=85',
        'color_fondo': '#0ea5e9',
        'color_texto': '#ffffff',
        'posicion': 0,
    },
    {
        'nombre': 'Categoría — Moda',
        'tipo': 'categoria',
        'titulo_es': 'Moda femenina',
        'subtitulo_es': 'Piezas atemporales para el día a día',
        'texto_cta_es': 'Explorar',
        'enlace_cta': '/shop/category/womens',
        'imagen_url': 'https://images.unsplash.com/photo-1483985988355-763728e1935b?w=1600&q=85',
        'imagen_movil_url': 'https://images.unsplash.com/photo-1483985988355-763728e1935b?w=800&q=85',
        'color_fondo': '#f3f4f6',
        'color_texto': '#111827',
        'posicion': 1,
    },
]


def fix_banners(apps, schema_editor):
    Banner = apps.get_model('marketing', 'Banner')
    Popup = apps.get_model('marketing', 'Popup')
    Promocion = apps.get_model('marketing', 'Promocion')

    now = timezone.now()
    start = now - timedelta(days=1)
    far_future = now + timedelta(days=3650)

    # Clear expiry on banners/popups (nullable fecha_fin)
    Banner.objects.all().update(fecha_fin=None, es_activo=True)
    Popup.objects.all().update(fecha_fin=None, es_activo=True)
    # Promocion.fecha_fin is NOT NULL — use a far-future date instead
    Promocion.objects.all().update(fecha_fin=far_future, es_activo=True)

    # Create seed banners if they don't exist
    for data in BANNERS:
        nombre = data.pop('nombre')
        Banner.objects.update_or_create(
            nombre=nombre,
            defaults={
                **data,
                'es_activo': True,
                'fecha_inicio': start,
                'fecha_fin': None,
            },
        )
        data['nombre'] = nombre  # restore for idempotency


class Migration(migrations.Migration):

    dependencies = [
        ('marketing', '0006_seed_sitetheme'),
    ]

    operations = [
        migrations.RunPython(fix_banners, migrations.RunPython.noop),
    ]
