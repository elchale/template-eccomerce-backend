import django_filters
from django.db import models

from products.models import Product


class ProductFilter(django_filters.FilterSet):
    min_price = django_filters.NumberFilter(
        field_name='base_price', lookup_expr='gte'
    )
    max_price = django_filters.NumberFilter(
        field_name='base_price', lookup_expr='lte'
    )
    category = django_filters.CharFilter(
        field_name='category__slug', lookup_expr='exact'
    )
    min_rating = django_filters.NumberFilter(
        field_name='average_rating', lookup_expr='gte'
    )
    is_featured = django_filters.BooleanFilter(field_name='is_featured')
    is_active = django_filters.BooleanFilter(field_name='is_active')
    search = django_filters.CharFilter(method='filter_search')

    class Meta:
        model = Product
        fields = [
            'min_price',
            'max_price',
            'category',
            'min_rating',
            'is_featured',
            'is_active',
            'search',
        ]

    def filter_search(self, queryset, name, value):
        return queryset.filter(
            models.Q(name__icontains=value)
            | models.Q(description__icontains=value)
        )
