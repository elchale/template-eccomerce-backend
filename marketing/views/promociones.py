from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from rest_framework import generics, viewsets
from rest_framework.permissions import AllowAny, IsAdminUser

from marketing.cache_keys import ACTIVE_PROMOCIONES_CACHE_KEY
from marketing.models import Promocion
from marketing.serializers.promociones import PromocionListSerializer, PromocionSerializer


class ActivePromocionListView(generics.ListAPIView):
    """
    GET - Public list of active promotions filtered by es_activo=True
    and within the valid date range. Cached for 2 minutes.
    """
    permission_classes = [AllowAny]
    serializer_class = PromocionListSerializer

    def get_queryset(self):
        now = timezone.now()
        return (
            Promocion.objects
            .filter(
                es_activo=True,
                fecha_inicio__lte=now,
                fecha_fin__gte=now,
            )
            .prefetch_related('productos', 'categorias')
            .order_by('-prioridad', '-created')
        )

    @method_decorator(cache_page(60 * 2, key_prefix=ACTIVE_PROMOCIONES_CACHE_KEY))
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)


class AdminPromocionViewSet(viewsets.ModelViewSet):
    """
    Admin CRUD for promotions.
    """
    permission_classes = [IsAdminUser]
    serializer_class = PromocionSerializer
    queryset = (
        Promocion.objects
        .prefetch_related('productos', 'categorias')
        .order_by('-prioridad', '-created')
    )
