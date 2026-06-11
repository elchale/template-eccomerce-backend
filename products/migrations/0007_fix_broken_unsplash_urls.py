"""One-time data migration: replace 6 unsplash photo URLs that now
return HTTP 404 (photos removed from Unsplash)."""

from django.db import migrations

REPLACEMENTS = {
    # Primary images
    'photo-1546868871-af0de0ae72be': 'photo-1523275335684-37898b6baf30',  # Apple Watch Ultra 2
    'photo-1614975059251-992f11792571': 'photo-1620799140408-edc6dcb6d633',  # Suéter de Lana Merino
    'photo-1507473885765-e6ed057ab6fe': 'photo-1513506003901-1e6a229e2d15',  # Lámpara de Escritorio
    # Secondary / gallery images
    'photo-1591337676887-a217a6c6bff3': 'photo-1592899677977-9c10ca588bbd',  # iPhone camera detail
    'photo-1588423771073-b8903fde1c68': 'photo-1583394838336-acd977736f90',  # AirPods Pro detail
    'photo-1514432324607-a09d9b4aefda': 'photo-1495474472287-4d71bcdd2085',  # Coffee Set detail
}


def fix_urls(apps, schema_editor):
    ProductImage = apps.get_model('products', 'ProductImage')
    for old_id, new_id in REPLACEMENTS.items():
        ProductImage.objects.filter(
            image_url__contains=old_id,
        ).update(
            image_url=f'https://images.unsplash.com/{new_id}?w=800&q=80',
        )


class Migration(migrations.Migration):

    dependencies = [
        ('products', '0006_fix_missing_product_images'),
    ]

    operations = [
        migrations.RunPython(fix_urls, migrations.RunPython.noop),
    ]
