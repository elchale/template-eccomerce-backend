from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("products", "0002_alter_productvariant_options_and_more"),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name="variantoption",
            unique_together={("variant_type", "value")},
        ),
        migrations.AddField(
            model_name="category",
            name="description_en",
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="category",
            name="description_es",
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="category",
            name="description_pt",
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="category",
            name="name_en",
            field=models.CharField(max_length=255, null=True),
        ),
        migrations.AddField(
            model_name="category",
            name="name_es",
            field=models.CharField(max_length=255, null=True),
        ),
        migrations.AddField(
            model_name="category",
            name="name_pt",
            field=models.CharField(max_length=255, null=True),
        ),
        migrations.AddField(
            model_name="product",
            name="description_en",
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="product",
            name="description_es",
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="product",
            name="description_pt",
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="product",
            name="name_en",
            field=models.CharField(max_length=255, null=True),
        ),
        migrations.AddField(
            model_name="product",
            name="name_es",
            field=models.CharField(max_length=255, null=True),
        ),
        migrations.AddField(
            model_name="product",
            name="name_pt",
            field=models.CharField(max_length=255, null=True),
        ),
        migrations.AddField(
            model_name="variantoption",
            name="value_en",
            field=models.CharField(max_length=100, null=True),
        ),
        migrations.AddField(
            model_name="variantoption",
            name="value_es",
            field=models.CharField(max_length=100, null=True),
        ),
        migrations.AddField(
            model_name="variantoption",
            name="value_pt",
            field=models.CharField(max_length=100, null=True),
        ),
        migrations.AddField(
            model_name="varianttype",
            name="name_en",
            field=models.CharField(max_length=100, null=True, unique=True),
        ),
        migrations.AddField(
            model_name="varianttype",
            name="name_es",
            field=models.CharField(max_length=100, null=True, unique=True),
        ),
        migrations.AddField(
            model_name="varianttype",
            name="name_pt",
            field=models.CharField(max_length=100, null=True, unique=True),
        ),
        migrations.AlterUniqueTogether(
            name="variantoption",
            unique_together={
                ("variant_type", "value"),
                ("variant_type", "value_en"),
                ("variant_type", "value_es"),
                ("variant_type", "value_pt"),
            },
        ),
    ]
