"""Serializer for UserAddress CRUD."""
from rest_framework import serializers

from users.models import UserAddress


class UserAddressSerializer(serializers.ModelSerializer):
    """Create / update / list user addresses.

    The ``user`` field is set from the request context, never from the payload.
    """

    class Meta:
        model = UserAddress
        fields = [
            'id',
            'label',
            'recipient_name',
            'phone',
            'street',
            'street_2',
            'city',
            'state',
            'postal_code',
            'country',
            'is_default_shipping',
            'is_default_billing',
            'created',
            'updated',
        ]
        read_only_fields = ['id', 'created', 'updated']

    def validate_recipient_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError('El nombre del destinatario no puede estar vacío.')
        return value

    def validate_street(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError('La dirección no puede estar vacía.')
        return value

    def validate_city(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError('La ciudad no puede estar vacía.')
        return value

    def create(self, validated_data):
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)
