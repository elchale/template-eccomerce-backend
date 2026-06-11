"""One-time data migration: add a placeholder image to every product
that has none, and replace unreliable picsum.photos URLs with unsplash."""

from django.db import migrations


PLACEHOLDER_POOL = [
    'https://images.unsplash.com/photo-1523275335684-37898b6baf30?w=800&q=80',
    'https://images.unsplash.com/photo-1505740420928-5e560c06d30e?w=800&q=80',
    'https://images.unsplash.com/photo-1526170375885-4d8ecf77b99f?w=800&q=80',
    'https://images.unsplash.com/photo-1572635196237-14b3f281503f?w=800&q=80',
    'https://images.unsplash.com/photo-1560343090-f0409e92791a?w=800&q=80',
]


def fix_images(apps, schema_editor):
    Product = apps.get_model('products', 'Product')
    ProductImage = apps.get_model('products', 'ProductImage')

    # Add a fallback image to every product that has zero images
    products_without_images = Product.objects.filter(images__isnull=True)
    for i, product in enumerate(products_without_images):
        url = PLACEHOLDER_POOL[i % len(PLACEHOLDER_POOL)]
        ProductImage.objects.create(
            product=product,
            image_url=url,
            alt_text='Producto',
            sort_order=0,
            is_primary=True,
        )

    # Replace all picsum.photos URLs — rotate through the pool
    picsum_images = ProductImage.objects.filter(
        image_url__contains='picsum.photos',
    )
    for i, img in enumerate(picsum_images):
        img.image_url = PLACEHOLDER_POOL[i % len(PLACEHOLDER_POOL)]
        img.save(update_fields=['image_url'])


class Migration(migrations.Migration):

    dependencies = [
        ('products', '0005_productimage_srcset_url_productimage_thumbnail_url_and_more'),
    ]

    operations = [
        migrations.RunPython(fix_images, migrations.RunPython.noop),
    ]
