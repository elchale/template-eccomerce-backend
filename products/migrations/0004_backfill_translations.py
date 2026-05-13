from django.db import migrations


def backfill_products(apps, schema_editor):
    Category = apps.get_model('products', 'Category')
    for obj in Category.objects.all():
        obj.name_es = obj.name or ''
        obj.description_es = obj.description or ''
        obj.save(update_fields=['name_es', 'description_es'])

    Product = apps.get_model('products', 'Product')
    for obj in Product.objects.all():
        obj.name_es = obj.name or ''
        obj.description_es = obj.description or ''
        obj.save(update_fields=['name_es', 'description_es'])

    VariantType = apps.get_model('products', 'VariantType')
    for obj in VariantType.objects.all():
        obj.name_es = obj.name or ''
        obj.save(update_fields=['name_es'])

    VariantOption = apps.get_model('products', 'VariantOption')
    for obj in VariantOption.objects.all():
        obj.value_es = obj.value or ''
        obj.save(update_fields=['value_es'])


class Migration(migrations.Migration):

    dependencies = [
        ('products', '0003_alter_variantoption_unique_together_and_more'),
    ]

    operations = [
        migrations.RunPython(backfill_products, migrations.RunPython.noop),
    ]
