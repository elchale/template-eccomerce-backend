from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("coupons", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="coupon",
            name="description_en",
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="coupon",
            name="description_es",
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="coupon",
            name="description_pt",
            field=models.TextField(blank=True, null=True),
        ),
    ]
