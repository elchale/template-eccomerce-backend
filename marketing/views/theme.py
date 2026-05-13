from django.core.cache import cache
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from marketing.cache_keys import SITE_THEME_CACHE_KEY, SITE_THEME_CACHE_TTL
from marketing.models import SiteTheme
from marketing.serializers.theme import SiteThemeAdminSerializer, SiteThemePublicSerializer, SiteThemeSerializer


class PublicThemeView(APIView):
    """
    GET /api/marketing/theme/
    Returns the active site theme (theme_id + custom_colors).
    Response is cached for SITE_THEME_CACHE_TTL seconds.
    AllowAny — called on every page load by ThemeProvider.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        cached = cache.get(SITE_THEME_CACHE_KEY)
        if cached is not None:
            return Response(cached)

        theme = SiteTheme.load()
        data = SiteThemePublicSerializer(theme).data
        cache.set(SITE_THEME_CACHE_KEY, data, SITE_THEME_CACHE_TTL)
        return Response(data)


class AdminThemeView(APIView):
    """
    GET  /api/admin/marketing/theme/  — returns current theme + catalog metadata.
    PUT  /api/admin/marketing/theme/  — updates theme_id and/or custom_colors.
    PATCH /api/admin/marketing/theme/ — alias for PUT (partial update).
    IsAdminUser required.
    """
    permission_classes = [IsAdminUser]

    def get(self, request):
        theme = SiteTheme.load()
        serializer = SiteThemeAdminSerializer(theme)
        return Response(serializer.data)

    def put(self, request):
        return self._update(request, partial=False)

    def patch(self, request):
        return self._update(request, partial=True)

    def _update(self, request, partial):
        theme = SiteTheme.load()
        serializer = SiteThemeSerializer(theme, data=request.data, partial=partial)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        serializer.save()
        cache.delete(SITE_THEME_CACHE_KEY)
        return Response(serializer.data)


class AdminThemeResetView(APIView):
    """
    POST /api/admin/marketing/theme/reset/
    Clears custom_colors back to {} without touching theme_id.
    IsAdminUser required.
    """
    permission_classes = [IsAdminUser]

    def post(self, request):
        theme = SiteTheme.load()
        theme.custom_colors = {}
        theme.save(update_fields=['custom_colors', 'updated'])
        cache.delete(SITE_THEME_CACHE_KEY)
        serializer = SiteThemeSerializer(theme)
        return Response(serializer.data)
