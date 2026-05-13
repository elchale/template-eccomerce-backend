from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("marketing", "0002_seed_site_config"),
    ]

    operations = [
        migrations.AddField(
            model_name="banner",
            name="subtitulo_en",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name="banner",
            name="subtitulo_es",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name="banner",
            name="subtitulo_pt",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name="banner",
            name="texto_cta_en",
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
        migrations.AddField(
            model_name="banner",
            name="texto_cta_es",
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
        migrations.AddField(
            model_name="banner",
            name="texto_cta_pt",
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
        migrations.AddField(
            model_name="banner",
            name="titulo_en",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name="banner",
            name="titulo_es",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name="banner",
            name="titulo_pt",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name="popup",
            name="mensaje_en",
            field=models.TextField(null=True),
        ),
        migrations.AddField(
            model_name="popup",
            name="mensaje_es",
            field=models.TextField(null=True),
        ),
        migrations.AddField(
            model_name="popup",
            name="mensaje_pt",
            field=models.TextField(null=True),
        ),
        migrations.AddField(
            model_name="popup",
            name="texto_cta_en",
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
        migrations.AddField(
            model_name="popup",
            name="texto_cta_es",
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
        migrations.AddField(
            model_name="popup",
            name="texto_cta_pt",
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
        migrations.AddField(
            model_name="popup",
            name="titulo_en",
            field=models.CharField(max_length=255, null=True),
        ),
        migrations.AddField(
            model_name="popup",
            name="titulo_es",
            field=models.CharField(max_length=255, null=True),
        ),
        migrations.AddField(
            model_name="popup",
            name="titulo_pt",
            field=models.CharField(max_length=255, null=True),
        ),
        migrations.AddField(
            model_name="promocion",
            name="nombre_en",
            field=models.CharField(max_length=255, null=True),
        ),
        migrations.AddField(
            model_name="promocion",
            name="nombre_es",
            field=models.CharField(max_length=255, null=True),
        ),
        migrations.AddField(
            model_name="promocion",
            name="nombre_pt",
            field=models.CharField(max_length=255, null=True),
        ),
    ]
