from django.db import migrations


def backfill_marketing(apps, schema_editor):
    Banner = apps.get_model('marketing', 'Banner')
    for obj in Banner.objects.all():
        obj.titulo_es = obj.titulo or ''
        obj.subtitulo_es = obj.subtitulo or ''
        obj.texto_cta_es = obj.texto_cta or ''
        obj.save(update_fields=['titulo_es', 'subtitulo_es', 'texto_cta_es'])

    Popup = apps.get_model('marketing', 'Popup')
    for obj in Popup.objects.all():
        obj.titulo_es = obj.titulo or ''
        obj.mensaje_es = obj.mensaje or ''
        obj.texto_cta_es = obj.texto_cta or ''
        obj.save(update_fields=['titulo_es', 'mensaje_es', 'texto_cta_es'])

    Promocion = apps.get_model('marketing', 'Promocion')
    for obj in Promocion.objects.all():
        obj.nombre_es = obj.nombre or ''
        obj.save(update_fields=['nombre_es'])


class Migration(migrations.Migration):

    dependencies = [
        ('marketing', '0003_banner_subtitulo_en_banner_subtitulo_es_and_more'),
    ]

    operations = [
        migrations.RunPython(backfill_marketing, migrations.RunPython.noop),
    ]
