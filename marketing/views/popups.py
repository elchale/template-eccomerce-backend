from django.db.models import Q
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from rest_framework import generics, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAdminUser
from rest_framework.response import Response

from core.utils.gcs import upload_image
from marketing.cache_keys import ACTIVE_POPUPS_CACHE_KEY
from marketing.models import Popup
from marketing.serializers.popups import PopupListSerializer, PopupSerializer


class ActivePopupListView(generics.ListAPIView):
    """
    GET - Public list of active popups. Optionally filter by ?tipo=<tipo>.
    Only popups with es_activo=True and within the valid date window are returned.
    Cached for 5 minutes (per tipo).
    """
    permission_classes = [AllowAny]
    serializer_class = PopupListSerializer

    def get_queryset(self):
        now = timezone.now()
        tipo = self.request.query_params.get('tipo')

        qs = Popup.objects.filter(
            es_activo=True,
        ).filter(
            Q(fecha_inicio__isnull=True) | Q(fecha_inicio__lte=now),
        ).filter(
            Q(fecha_fin__isnull=True) | Q(fecha_fin__gte=now),
        ).order_by('-created')

        if tipo:
            qs = qs.filter(tipo=tipo)

        return qs

    @method_decorator(cache_page(60 * 5, key_prefix=ACTIVE_POPUPS_CACHE_KEY))
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)


class AdminPopupViewSet(viewsets.ModelViewSet):
    """
    Admin CRUD for popups.
    """
    permission_classes = [IsAdminUser]
    serializer_class = PopupSerializer
    queryset = Popup.objects.order_by('-created')

    @action(detail=True, methods=['post'], url_path='upload-image')
    def upload_image(self, request, pk=None):
        """
        POST /api/admin/marketing/popups/{id}/upload-image/
        Upload an image for a popup via GCS.
        Returns {image_url: "..."}.
        """
        popup = self.get_object()
        image_file = request.FILES.get('image')
        if not image_file:
            return Response(
                {'detail': 'No image file provided.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            image_url = upload_image(image_file, folder=f'marketing/popups/{popup.pk}')
        except Exception as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        popup.imagen_url = image_url
        popup.save(update_fields=['imagen_url'])

        return Response({'image_url': image_url}, status=status.HTTP_200_OK)
