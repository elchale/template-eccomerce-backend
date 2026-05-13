from rest_framework import serializers

from marketing.models import ConfiguracionTienda


class ConfiguracionSerializer(serializers.ModelSerializer):
    """Serializer for store configuration key-value pairs."""

    class Meta:
        model = ConfiguracionTienda
        fields = [
            'id',
            'clave',
            'valor',
            'descripcion',
            'created',
            'updated',
        ]
        read_only_fields = ['id', 'created', 'updated']

    def validate_clave(self, value):
        if not value.strip():
            raise serializers.ValidationError('La clave no puede estar vacía.')
        return value.strip()
