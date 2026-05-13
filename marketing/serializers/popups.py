from rest_framework import serializers

from marketing.models import Popup


class PopupListSerializer(serializers.ModelSerializer):
    """Public read-only serializer for listing active popups."""

    class Meta:
        model = Popup
        fields = [
            'id',
            'nombre',
            'tipo',
            'titulo',
            'mensaje',
            'imagen_url',
            'texto_cta',
            'enlace_cta',
            'codigo_cupon',
            'retraso_segundos',
            'frecuencia_horas',
        ]
        read_only_fields = fields


class PopupSerializer(serializers.ModelSerializer):
    """Admin full CRUD serializer for popups with per-language translation columns."""

    titulo_es = serializers.CharField(allow_blank=False, required=True)
    titulo_en = serializers.CharField(allow_blank=True, required=False, allow_null=True, default='')
    titulo_pt = serializers.CharField(allow_blank=True, required=False, allow_null=True, default='')
    mensaje_es = serializers.CharField(allow_blank=False, required=True)
    mensaje_en = serializers.CharField(allow_blank=True, required=False, allow_null=True, default='')
    mensaje_pt = serializers.CharField(allow_blank=True, required=False, allow_null=True, default='')
    texto_cta_es = serializers.CharField(allow_blank=True, required=False, default='')
    texto_cta_en = serializers.CharField(allow_blank=True, required=False, allow_null=True, default='')
    texto_cta_pt = serializers.CharField(allow_blank=True, required=False, allow_null=True, default='')

    class Meta:
        model = Popup
        fields = [
            'id',
            'nombre',
            'tipo',
            'titulo',
            'titulo_es',
            'titulo_en',
            'titulo_pt',
            'mensaje',
            'mensaje_es',
            'mensaje_en',
            'mensaje_pt',
            'imagen_url',
            'texto_cta',
            'texto_cta_es',
            'texto_cta_en',
            'texto_cta_pt',
            'enlace_cta',
            'codigo_cupon',
            'retraso_segundos',
            'frecuencia_horas',
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
        retraso = data.get('retraso_segundos')
        if retraso is not None and retraso < 0:
            raise serializers.ValidationError(
                {'retraso_segundos': 'El retraso no puede ser negativo.'}
            )
        frecuencia = data.get('frecuencia_horas')
        if frecuencia is not None and frecuencia < 0:
            raise serializers.ValidationError(
                {'frecuencia_horas': 'La frecuencia no puede ser negativa.'}
            )
        return data
