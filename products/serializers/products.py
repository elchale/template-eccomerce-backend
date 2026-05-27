from rest_framework import serializers

from products.models import (
    Product,
    ProductImage,
    ProductVariant,
    VariantOption,
    VariantType,
)
from products.pricing import (
    effective_unit_price,
    get_active_promo_for_product,
)

# Re-exported for backwards compatibility — the single implementation now
# lives in products/pricing.py.
_get_active_promo_for_product = get_active_promo_for_product


def _calculate_precio_promocion(product, promo):
    """
    Calculate the discounted display price for a PRODUCT (no variant) given an
    active promotion. Returns the discounted price as a Decimal, or ``None``
    when the promo does not produce a per-unit reduction (no promo, or a
    COMPRA_X_LLEVA_Y promo) so the product page keeps showing the base price.

    Thin wrapper over the shared variant-aware ``effective_unit_price`` so there
    is a single discount implementation.
    """
    if promo is None:
        return None

    from marketing.models import Promocion

    if promo.tipo not in (Promocion.Tipo.PORCENTAJE, Promocion.Tipo.MONTO_FIJO):
        # COMPRA_X_LLEVA_Y doesn't reduce the per-unit price directly.
        return None

    return effective_unit_price(product, None, promo)


class ProductImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductImage
        fields = [
            'id',
            'image_url',
            'alt_text',
            'sort_order',
            'is_primary',
        ]
        read_only_fields = ['id']


class VariantTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = VariantType
        fields = ['id', 'name']
        read_only_fields = ['id']


class VariantOptionSerializer(serializers.ModelSerializer):
    variant_type_name = serializers.CharField(
        source='variant_type.name', read_only=True
    )

    class Meta:
        model = VariantOption
        fields = ['id', 'variant_type', 'variant_type_name', 'value']
        read_only_fields = ['id']


class ProductVariantSerializer(serializers.ModelSerializer):
    options = VariantOptionSerializer(many=True, read_only=True)

    class Meta:
        model = ProductVariant
        fields = [
            'id',
            'sku',
            'price',
            'stock',
            'options',
            'image_url',
            'is_active',
        ]
        read_only_fields = ['id']


class ProductListSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(
        source='category.name', read_only=True, default=None
    )
    category_slug = serializers.CharField(
        source='category.slug', read_only=True, default=None
    )
    primary_image = serializers.SerializerMethodField()
    precio_promocion = serializers.SerializerMethodField()
    promocion = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            'id',
            'name',
            'slug',
            'base_price',
            'compare_at_price',
            'precio_promocion',
            'promocion',
            'is_active',
            'is_featured',
            'sku',
            'stock',
            'average_rating',
            'review_count',
            'category',
            'category_name',
            'category_slug',
            'primary_image',
            'created',
        ]
        read_only_fields = ['id', 'created']

    def get_primary_image(self, obj):
        # Use prefetched images to avoid N+1 queries.
        images = list(obj.images.all())
        primary = next((img for img in images if img.is_primary), None)
        if not primary and images:
            primary = images[0]
        if primary:
            return ProductImageSerializer(primary).data
        return None

    def _get_promo(self, obj):
        active_promos = self.context.get('active_promos')
        return _get_active_promo_for_product(obj, active_promos=active_promos)

    def get_precio_promocion(self, obj):
        promo = self._get_promo(obj)
        price = _calculate_precio_promocion(obj, promo)
        return str(price) if price is not None else None

    def get_promocion(self, obj):
        promo = self._get_promo(obj)
        if promo is None:
            return None
        return {
            'id': promo.id,
            'nombre': promo.nombre,
            'slug': promo.slug,
            'tipo': promo.tipo,
            'valor_descuento': str(promo.valor_descuento),
            'es_flash_sale': promo.es_flash_sale,
        }


class ProductDetailSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(
        source='category.name', read_only=True, default=None
    )
    category_slug = serializers.CharField(
        source='category.slug', read_only=True, default=None
    )
    images = ProductImageSerializer(many=True, read_only=True)
    variants = ProductVariantSerializer(many=True, read_only=True)
    precio_promocion = serializers.SerializerMethodField()
    promocion = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            'id',
            'name',
            'slug',
            'description',
            'base_price',
            'compare_at_price',
            'precio_promocion',
            'promocion',
            'is_active',
            'is_featured',
            'sku',
            'stock',
            'average_rating',
            'review_count',
            'category',
            'category_name',
            'category_slug',
            'images',
            'variants',
            'created',
            'updated',
        ]
        read_only_fields = ['id', 'average_rating', 'review_count', 'created', 'updated']

    def _get_promo(self, obj):
        active_promos = self.context.get('active_promos')
        return _get_active_promo_for_product(obj, active_promos=active_promos)

    def get_precio_promocion(self, obj):
        promo = self._get_promo(obj)
        price = _calculate_precio_promocion(obj, promo)
        return str(price) if price is not None else None

    def get_promocion(self, obj):
        promo = self._get_promo(obj)
        if promo is None:
            return None
        return {
            'id': promo.id,
            'nombre': promo.nombre,
            'slug': promo.slug,
            'tipo': promo.tipo,
            'valor_descuento': str(promo.valor_descuento),
            'es_flash_sale': promo.es_flash_sale,
        }


class AdminProductSerializer(serializers.ModelSerializer):
    images = ProductImageSerializer(many=True, read_only=True)
    variants = ProductVariantSerializer(many=True, read_only=True)
    primary_image = serializers.SerializerMethodField()
    category_name = serializers.CharField(source='category.name', read_only=True)
    category_slug = serializers.CharField(source='category.slug', read_only=True)

    # Per-language translation fields
    name_es = serializers.CharField(allow_blank=False, required=True)
    name_en = serializers.CharField(allow_blank=True, required=False, allow_null=True, default='')
    name_pt = serializers.CharField(allow_blank=True, required=False, allow_null=True, default='')
    description_es = serializers.CharField(allow_blank=True, required=False, default='')
    description_en = serializers.CharField(allow_blank=True, required=False, allow_null=True, default='')
    description_pt = serializers.CharField(allow_blank=True, required=False, allow_null=True, default='')

    class Meta:
        model = Product
        fields = [
            'id',
            'name',
            'slug',
            'description',
            'name_es',
            'name_en',
            'name_pt',
            'description_es',
            'description_en',
            'description_pt',
            'base_price',
            'compare_at_price',
            'is_active',
            'is_featured',
            'sku',
            'stock',
            'average_rating',
            'review_count',
            'category',
            'category_name',
            'category_slug',
            'primary_image',
            'images',
            'variants',
            'created',
            'updated',
        ]
        read_only_fields = ['id', 'average_rating', 'review_count', 'created', 'updated']

    def get_primary_image(self, obj):
        primary = obj.images.filter(is_primary=True).first() or obj.images.order_by('sort_order', 'id').first()
        if primary:
            return ProductImageSerializer(primary).data
        return None


class AdminProductImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductImage
        fields = [
            'id',
            'product',
            'image_url',
            'alt_text',
            'sort_order',
            'is_primary',
        ]
        read_only_fields = ['id', 'image_url']


class AdminVariantTypeSerializer(serializers.ModelSerializer):
    """Admin serializer for VariantType exposing per-language name columns."""

    name_es = serializers.CharField(allow_blank=False, required=True)
    name_en = serializers.CharField(allow_blank=True, required=False, allow_null=True, default='')
    name_pt = serializers.CharField(allow_blank=True, required=False, allow_null=True, default='')

    class Meta:
        model = VariantType
        fields = [
            'id',
            'name',
            'name_es',
            'name_en',
            'name_pt',
            'created',
            'updated',
        ]
        read_only_fields = ['id', 'created', 'updated']


class AdminVariantOptionSerializer(serializers.ModelSerializer):
    """Admin serializer for VariantOption exposing per-language value columns."""

    variant_type_name = serializers.CharField(source='variant_type.name', read_only=True)
    value_es = serializers.CharField(allow_blank=False, required=True)
    value_en = serializers.CharField(allow_blank=True, required=False, allow_null=True, default='')
    value_pt = serializers.CharField(allow_blank=True, required=False, allow_null=True, default='')

    class Meta:
        model = VariantOption
        fields = [
            'id',
            'variant_type',
            'variant_type_name',
            'value',
            'value_es',
            'value_en',
            'value_pt',
            'created',
            'updated',
        ]
        read_only_fields = ['id', 'created', 'updated']
