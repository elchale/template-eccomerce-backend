from rest_framework import serializers

from products.models import Product, Wishlist
from products.serializers.products import ProductListSerializer


class WishlistSerializer(serializers.ModelSerializer):
    product = ProductListSerializer(read_only=True)

    class Meta:
        model = Wishlist
        fields = ['id', 'product', 'created']
        read_only_fields = ['id', 'created']


class WishlistToggleSerializer(serializers.Serializer):
    product_id = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.filter(is_active=True),
        source='product',
    )
