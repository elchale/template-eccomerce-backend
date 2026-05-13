from rest_framework import serializers

from marketing.models import Promocion


class PromocionListSerializer(serializers.ModelSerializer):
    """Public read-only serializer for listing active promotions."""

    class Meta:
        model = Promocion
        fields = [
            'id',
            'nombre',
            'slug',
            'tipo',
            'valor_descuento',
            'compra_cantidad',
            'lleva_cantidad',
            'aplica_a_todo',
            'fecha_inicio',
            'fecha_fin',
            'es_flash_sale',
            'prioridad',
        ]
        read_only_fields = fields


class PromocionSerializer(serializers.ModelSerializer):
    """Admin full CRUD serializer for promotions with per-language translation columns."""

    nombre_es = serializers.CharField(allow_blank=False, required=True)
    nombre_en = serializers.CharField(allow_blank=True, required=False, allow_null=True, default='')
    nombre_pt = serializers.CharField(allow_blank=True, required=False, allow_null=True, default='')

    class Meta:
        model = Promocion
        fields = [
            'id',
            'nombre',
            'nombre_es',
            'nombre_en',
            'nombre_pt',
            'slug',
            'tipo',
            'valor_descuento',
            'compra_cantidad',
            'lleva_cantidad',
            'productos',
            'categorias',
            'aplica_a_todo',
            'fecha_inicio',
            'fecha_fin',
            'es_flash_sale',
            'limite_uso',
            'usos_actuales',
            'es_activo',
            'prioridad',
            'created',
            'updated',
        ]
        read_only_fields = ['id', 'usos_actuales', 'created', 'updated']

    def validate(self, data):
        fecha_inicio = data.get('fecha_inicio')
        fecha_fin = data.get('fecha_fin')
        if fecha_inicio and fecha_fin and fecha_inicio >= fecha_fin:
            raise serializers.ValidationError(
                {'fecha_fin': 'La fecha de fin debe ser posterior a la fecha de inicio.'}
            )

        tipo = data.get('tipo')
        if tipo == Promocion.Tipo.COMPRA_X_LLEVA_Y:
            if not data.get('compra_cantidad'):
                raise serializers.ValidationError(
                    {'compra_cantidad': 'Requerido para el tipo Compra X Lleva Y.'}
                )
            if not data.get('lleva_cantidad'):
                raise serializers.ValidationError(
                    {'lleva_cantidad': 'Requerido para el tipo Compra X Lleva Y.'}
                )

        valor = data.get('valor_descuento')
        if tipo == Promocion.Tipo.PORCENTAJE and valor is not None and valor > 100:
            raise serializers.ValidationError(
                {'valor_descuento': 'El porcentaje no puede exceder 100.'}
            )

        return data
