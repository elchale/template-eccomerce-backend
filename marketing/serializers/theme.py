import re

from rest_framework import serializers

from marketing.models import SiteTheme
from marketing.theme_constants import ALLOWED_CUSTOM_COLOR_KEYS, VALID_THEME_IDS

_HEX_RE = re.compile(r'^#([0-9A-Fa-f]{6}|[0-9A-Fa-f]{8})$')


class SiteThemePublicSerializer(serializers.ModelSerializer):
    """Read-only serializer for the public /api/marketing/theme/ endpoint."""

    class Meta:
        model = SiteTheme
        fields = ['theme_id', 'custom_colors']
        read_only_fields = ['theme_id', 'custom_colors']


class SiteThemeSerializer(serializers.ModelSerializer):
    """
    Read/write serializer used for admin PUT/PATCH and POST /reset/ responses.
    Validates theme_id against VALID_THEME_IDS and each custom_colors entry
    against ALLOWED_CUSTOM_COLOR_KEYS + hex format.
    """

    class Meta:
        model = SiteTheme
        fields = ['theme_id', 'custom_colors']

    def validate_theme_id(self, value):
        if value not in VALID_THEME_IDS:
            valid = ', '.join(VALID_THEME_IDS)
            raise serializers.ValidationError(
                f'Tema no válido. Opciones: {valid}.'
            )
        return value

    def validate_custom_colors(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError('Se esperaba un objeto JSON.')

        errors = {}
        for key, hex_value in value.items():
            if key not in ALLOWED_CUSTOM_COLOR_KEYS:
                errors[key] = ['Variable CSS no permitida.']
            elif not _HEX_RE.match(str(hex_value)):
                errors[key] = ['Debe ser un color hex válido (#RRGGBB o #RRGGBBAA).']

        if errors:
            raise serializers.ValidationError(errors)

        return value


class SiteThemeAdminSerializer(SiteThemeSerializer):
    """
    Extended serializer for the admin GET endpoint.
    Adds catalog fields: available_theme_ids, customizable_color_keys, updated.
    """

    available_theme_ids = serializers.SerializerMethodField(read_only=True)
    customizable_color_keys = serializers.SerializerMethodField(read_only=True)
    updated = serializers.DateTimeField(read_only=True)

    class Meta(SiteThemeSerializer.Meta):
        fields = SiteThemeSerializer.Meta.fields + [
            'available_theme_ids',
            'customizable_color_keys',
            'updated',
        ]

    def get_available_theme_ids(self, obj):
        return list(VALID_THEME_IDS)

    def get_customizable_color_keys(self, obj):
        return list(ALLOWED_CUSTOM_COLOR_KEYS)
