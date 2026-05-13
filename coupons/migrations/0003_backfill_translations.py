from django.db import migrations


def backfill_coupons(apps, schema_editor):
    Coupon = apps.get_model('coupons', 'Coupon')
    for obj in Coupon.objects.all():
        obj.description_es = obj.description or ''
        obj.save(update_fields=['description_es'])


class Migration(migrations.Migration):

    dependencies = [
        ('coupons', '0002_coupon_description_en_coupon_description_es_and_more'),
    ]

    operations = [
        migrations.RunPython(backfill_coupons, migrations.RunPython.noop),
    ]
