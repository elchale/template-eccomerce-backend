from django.db.models import Count, Q
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from rest_framework import generics, viewsets
from rest_framework.permissions import AllowAny, IsAdminUser

from products.cache_keys import CATEGORY_DETAIL_CACHE_KEY, CATEGORY_LIST_CACHE_KEY
from products.models import Category
from products.serializers.categories import CategoryDetailSerializer, CategorySerializer


class CategoryListView(generics.ListAPIView):
    """
    Public endpoint that returns the category tree structure.
    Only root categories (parent=null) are returned, with nested children.
    """
    permission_classes = [AllowAny]
    serializer_class = CategorySerializer

    def get_queryset(self):
        return (
            Category.objects
            .filter(is_active=True, parent__isnull=True)
            .prefetch_related('children')
            .order_by('sort_order', 'name')
        )

    @method_decorator(cache_page(60 * 15, key_prefix=CATEGORY_LIST_CACHE_KEY))
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)


class CategoryDetailView(generics.RetrieveAPIView):
    """
    Public endpoint that returns a single category by slug.
    """
    permission_classes = [AllowAny]
    serializer_class = CategoryDetailSerializer
    lookup_field = 'slug'

    def get_queryset(self):
        return (
            Category.objects
            .filter(is_active=True)
            .prefetch_related('children')
            .annotate(
                product_count_annotated=Count(
                    'products', filter=Q(products__is_active=True)
                )
            )
        )

    @method_decorator(cache_page(60 * 15, key_prefix=CATEGORY_DETAIL_CACHE_KEY))
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)


class AdminCategoryViewSet(viewsets.ModelViewSet):
    """
    Admin CRUD for categories.
    """
    permission_classes = [IsAdminUser]
    serializer_class = CategoryDetailSerializer
    queryset = (
        Category.objects
        .prefetch_related('children')
        .annotate(
            product_count_annotated=Count(
                'products', filter=Q(products__is_active=True)
            )
        )
        .order_by('sort_order', 'name')
    )
