from django.core.cache import cache
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from marketing.cache_keys import CONFIGURACION_CACHE_KEY
from marketing.models import ConfiguracionTienda
from marketing.serializers.configuracion import ConfiguracionSerializer


class ConfiguracionView(APIView):
    """
    GET - Public endpoint returning all store configuration as a flat dict
    {clave: valor}.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        cached = cache.get(CONFIGURACION_CACHE_KEY)
        if cached is not None:
            return Response(cached)

        configs = ConfiguracionTienda.objects.all()
        result = {c.clave: c.valor for c in configs}
        cache.set(CONFIGURACION_CACHE_KEY, result, 60 * 10)
        return Response(result)


class AdminConfiguracionView(APIView):
    """
    Admin GET/PATCH for store configuration.
    GET returns all config objects.
    PATCH accepts a dict {clave: valor} and upserts each key.
    """
    permission_classes = [IsAdminUser]

    def get(self, request):
        configs = ConfiguracionTienda.objects.all()
        result = {c.clave: c.valor for c in configs}
        return Response(result)

    def patch(self, request):
        data = request.data
        if not isinstance(data, dict):
            return Response(
                {'detail': 'Se esperaba un objeto JSON con claves y valores.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        updated = []
        errors = {}
        for clave, valor in data.items():
            obj, _ = ConfiguracionTienda.objects.get_or_create(clave=clave)
            serializer = ConfiguracionSerializer(
                obj,
                data={'clave': clave, 'valor': str(valor), 'descripcion': obj.descripcion},
            )
            if serializer.is_valid():
                serializer.save()
                updated.append(serializer.data)
            else:
                errors[clave] = serializer.errors

        if errors:
            return Response(
                {'detail': 'Algunos valores no son válidos.', 'errors': errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Invalidate cache
        cache.delete(CONFIGURACION_CACHE_KEY)

        return Response(updated)
