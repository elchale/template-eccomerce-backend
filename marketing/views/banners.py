from django.db.models import Q
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from rest_framework import generics, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAdminUser
from rest_framework.response import Response

from core.utils.gcs import upload_image
from marketing.cache_keys import ACTIVE_BANNERS_CACHE_KEY
from marketing.models import Banner
from marketing.serializers.banners import BannerListSerializer, BannerSerializer


class ActiveBannerListView(generics.ListAPIView):
    """
    GET - Public list of active banners. Optionally filter by ?tipo=<tipo>.
    Only banners with es_activo=True and within the valid date window are returned.
    Cached for 5 minutes (per tipo).
    """
    permission_classes = [AllowAny]
    serializer_class = BannerListSerializer

    def get_queryset(self):
        now = timezone.now()
        tipo = self.request.query_params.get('tipo')

        qs = Banner.objects.filter(
            es_activo=True,
        ).filter(
            Q(fecha_inicio__isnull=True) | Q(fecha_inicio__lte=now),
        ).filter(
            Q(fecha_fin__isnull=True) | Q(fecha_fin__gte=now),
        ).order_by('posicion', '-created')

        if tipo:
            qs = qs.filter(tipo=tipo)

        return qs

    @method_decorator(cache_page(60 * 5, key_prefix=ACTIVE_BANNERS_CACHE_KEY))
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)


class AdminBannerViewSet(viewsets.ModelViewSet):
    """
    Admin CRUD for banners.
    """
    permission_classes = [IsAdminUser]
    serializer_class = BannerSerializer
    queryset = Banner.objects.order_by('posicion', '-created')

    @action(detail=True, methods=['post'], url_path='upload-image')
    def upload_image(self, request, pk=None):
        """
        POST /api/admin/marketing/banners/{id}/upload-image/
        Upload an image for a banner via GCS.
        Optional query param ?variant=desktop|mobile controls which URL field is updated.
        Returns {image_url: "..."}.
        """
        banner = self.get_object()
        image_file = request.FILES.get('image')
        if not image_file:
            return Response(
                {'detail': 'No image file provided.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            image_url = upload_image(image_file, folder=f'marketing/banners/{banner.pk}')
        except Exception as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        variant = request.query_params.get('variant', 'desktop')
        if variant == 'mobile':
            banner.imagen_movil_url = image_url
        else:
            banner.imagen_url = image_url
        banner.save(update_fields=['imagen_url'] if variant != 'mobile' else ['imagen_movil_url'])

        return Response({'image_url': image_url}, status=status.HTTP_200_OK)
