from rest_framework import serializers

from marketing.models import Banner


class BannerListSerializer(serializers.ModelSerializer):
    """Public read-only serializer for listing active banners."""

    class Meta:
        model = Banner
        fields = [
            'id',
            'nombre',
            'tipo',
            'titulo',
            'subtitulo',
            'texto_cta',
            'enlace_cta',
            'imagen_url',
            'imagen_movil_url',
            'color_fondo',
            'color_texto',
            'posicion',
        ]
        read_only_fields = fields


class BannerSerializer(serializers.ModelSerializer):
    """Admin full CRUD serializer for banners with per-language translation columns."""

    titulo_es = serializers.CharField(allow_blank=True, required=False, default='')
    titulo_en = serializers.CharField(allow_blank=True, required=False, allow_null=True, default='')
    titulo_pt = serializers.CharField(allow_blank=True, required=False, allow_null=True, default='')
    subtitulo_es = serializers.CharField(allow_blank=True, required=False, default='')
    subtitulo_en = serializers.CharField(allow_blank=True, required=False, allow_null=True, default='')
    subtitulo_pt = serializers.CharField(allow_blank=True, required=False, allow_null=True, default='')
    texto_cta_es = serializers.CharField(allow_blank=True, required=False, default='')
    texto_cta_en = serializers.CharField(allow_blank=True, required=False, allow_null=True, default='')
    texto_cta_pt = serializers.CharField(allow_blank=True, required=False, allow_null=True, default='')

    class Meta:
        model = Banner
        fields = [
            'id',
            'nombre',
            'tipo',
            'titulo',
            'titulo_es',
            'titulo_en',
            'titulo_pt',
            'subtitulo',
            'subtitulo_es',
            'subtitulo_en',
            'subtitulo_pt',
            'texto_cta',
            'texto_cta_es',
            'texto_cta_en',
            'texto_cta_pt',
            'enlace_cta',
            'imagen_url',
            'imagen_movil_url',
            'color_fondo',
            'color_texto',
            'posicion',
            'es_activo',
            'fecha_inicio',
            'fecha_fin',
            'created',
            'updated',
        ]
        read_only_fields = ['id', 'created', 'updated']

    def validate(self, data):
        fecha_inicio = data.get('fecha_inicio')
        fecha_fin = data.get('fecha_fin')
        if fecha_inicio and fecha_fin and fecha_inicio >= fecha_fin:
            raise serializers.ValidationError(
                {'fecha_fin': 'La fecha de fin debe ser posterior a la fecha de inicio.'}
            )
        return data
