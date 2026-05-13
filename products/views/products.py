from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import generics, status, viewsets, filters
from rest_framework.permissions import AllowAny, IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from core.utils.gcs import delete_file_from_url, upload_image
from products.cache_keys import PRODUCT_DETAIL_CACHE_KEY
from products.filters import ProductFilter
from products.models import (
    Product,
    ProductImage,
    ProductVariant,
    VariantType,
)
from products.serializers.products import (
    AdminProductSerializer,
    ProductDetailSerializer,
    ProductImageSerializer,
    ProductListSerializer,
    ProductVariantSerializer,
    VariantTypeSerializer,
)


def _get_active_promotions():
    """
    Fetch all currently active promotions with prefetched M2M relations.
    Returns a list sorted by -prioridad (highest first).
    """
    try:
        from marketing.models import Promocion
    except ImportError:
        return []

    now = timezone.now()
    return list(
        Promocion.objects.filter(
            es_activo=True,
            fecha_inicio__lte=now,
            fecha_fin__gte=now,
        )
        .prefetch_related('productos', 'categorias')
        .order_by('-prioridad')
    )


class ProductListView(generics.ListAPIView):
    """
    Public paginated product listing with filtering support.
    """
    permission_classes = [AllowAny]
    serializer_class = ProductListSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_class = ProductFilter

    def get_queryset(self):
        return (
            Product.objects
            .filter(is_active=True)
            .select_related('category')
            .prefetch_related('images')
        )

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['active_promos'] = _get_active_promotions()
        return context

    @method_decorator(cache_page(60 * 5))
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)


class ProductDetailView(generics.RetrieveAPIView):
    """
    Public product detail by slug.
    """
    permission_classes = [AllowAny]
    serializer_class = ProductDetailSerializer
    lookup_field = 'slug'

    def get_queryset(self):
        return (
            Product.objects
            .filter(is_active=True)
            .select_related('category')
            .prefetch_related('images', 'variants__options__variant_type')
        )

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['active_promos'] = _get_active_promotions()
        return context

    @method_decorator(cache_page(60 * 5, key_prefix=PRODUCT_DETAIL_CACHE_KEY))
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)


class AdminProductViewSet(viewsets.ModelViewSet):
    """
    Admin CRUD for products.
    """
    permission_classes = [IsAdminUser]
    serializer_class = AdminProductSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = ProductFilter
    search_fields = ['name', 'sku', 'description']
    ordering_fields = ['name', 'base_price', 'stock', 'created']
    ordering = ['-created']
    queryset = (
        Product.objects
        .select_related('category')
        .prefetch_related('images', 'variants__options__variant_type')
        .order_by('-created')
    )


class AdminProductImageView(APIView):
    """
    Admin endpoint for managing product images.
    POST: Upload a new image via GCS.
    DELETE: Remove an image.
    """
    permission_classes = [IsAdminUser]

    def post(self, request, product_id):
        try:
            product = Product.objects.get(pk=product_id)
        except Product.DoesNotExist:
            return Response(
                {'detail': 'Product not found.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        image_file = request.FILES.get('image')
        if not image_file:
            return Response(
                {'detail': 'No image file provided.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            image_url = upload_image(
                image_file,
                folder=f"products/{product.slug}",
            )
        except Exception as e:
            return Response(
                {'detail': str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        alt_text = request.data.get('alt_text', '')
        sort_order = request.data.get('sort_order', 0)
        is_primary = request.data.get('is_primary', False)

        # If this is marked as primary, unset other primaries
        if is_primary:
            product.images.filter(is_primary=True).update(is_primary=False)

        product_image = ProductImage.objects.create(
            product=product,
            image_url=image_url,
            alt_text=alt_text,
            sort_order=sort_order,
            is_primary=is_primary,
        )

        serializer = ProductImageSerializer(product_image)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def delete(self, request, product_id):
        image_id = request.data.get('image_id')
        if not image_id:
            return Response(
                {'detail': 'image_id is required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            image = ProductImage.objects.get(pk=image_id, product_id=product_id)
        except ProductImage.DoesNotExist:
            return Response(
                {'detail': 'Image not found.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Delete from GCS
        delete_file_from_url(image.image_url)
        image.delete()

        return Response(status=status.HTTP_204_NO_CONTENT)


class AdminProductVariantViewSet(viewsets.ModelViewSet):
    """
    Admin CRUD for product variants, scoped to a specific product.
    """
    permission_classes = [IsAdminUser]
    serializer_class = ProductVariantSerializer

    def get_queryset(self):
        return (
            ProductVariant.objects
            .filter(product_id=self.kwargs['product_id'])
            .prefetch_related('options__variant_type')
        )

    def perform_create(self, serializer):
        product_id = self.kwargs['product_id']
        try:
            product = Product.objects.get(pk=product_id)
        except Product.DoesNotExist:
            from rest_framework.exceptions import NotFound
            raise NotFound('Product not found.')
        serializer.save(product=product)


class AdminVariantTypeViewSet(viewsets.ModelViewSet):
    """
    Admin CRUD for variant types (e.g., Size, Color).
    """
    permission_classes = [IsAdminUser]
    serializer_class = VariantTypeSerializer
    queryset = VariantType.objects.all()
