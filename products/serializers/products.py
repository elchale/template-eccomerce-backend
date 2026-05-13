from decimal import Decimal

from django.utils import timezone
from rest_framework import serializers

from products.models import (
    Product,
    ProductImage,
    ProductVariant,
    VariantOption,
    VariantType,
)


def _get_active_promo_for_product(product, active_promos=None):
    """
    Return the highest-priority active Promocion that applies to this product
    (via product M2M, category M2M, or aplica_a_todo).
    Returns None if no active promotion applies.

    If active_promos is provided (prefetched list), checks in-memory instead of
    hitting the DB. The list must already be sorted by -prioridad.
    """
    if active_promos is not None:
        # In-memory lookup using prefetched promos (avoids N+1)
        product_id = product.pk
        category_id = product.category_id

        best_product_promo = None
        best_category_promo = None
        best_global_promo = None

        for promo in active_promos:
            # Check product-specific match (prefetched M2M)
            if not best_product_promo:
                promo_product_ids = {p.pk for p in promo.productos.all()}
                if product_id in promo_product_ids:
                    best_product_promo = promo

            # Check category match (prefetched M2M)
            if not best_category_promo and category_id:
                promo_category_ids = {c.pk for c in promo.categorias.all()}
                if category_id in promo_category_ids:
                    best_category_promo = promo

            # Check store-wide match
            if not best_global_promo and promo.aplica_a_todo:
                best_global_promo = promo

            # Early exit if we found the highest-priority match type
            if best_product_promo and best_category_promo and best_global_promo:
                break

        # Priority: product-specific > category > global
        return best_product_promo or best_category_promo or best_global_promo

    # Fallback: DB queries (used when context is not available)
    try:
        from marketing.models import Promocion
    except ImportError:
        return None

    now = timezone.now()
    base_qs = Promocion.objects.filter(
        es_activo=True,
        fecha_inicio__lte=now,
        fecha_fin__gte=now,
    ).order_by('-prioridad')

    # Check product-specific promos
    promo = base_qs.filter(productos=product).first()
    if promo:
        return promo

    # Check category promos
    if product.category_id:
        promo = base_qs.filter(categorias=product.category_id).first()
        if promo:
            return promo

    # Check store-wide promos
    return base_qs.filter(aplica_a_todo=True).first()


def _calculate_precio_promocion(product, promo):
    """
    Calculate the discounted price for a product given an active promotion.
    Returns the discounted price as a Decimal, or None if not applicable.
    """
    if promo is None:
        return None

    from marketing.models import Promocion

    base = product.base_price
    tipo = promo.tipo

    if tipo == Promocion.Tipo.PORCENTAJE:
        discount = (base * promo.valor_descuento / Decimal('100')).quantize(Decimal('0.01'))
        return max(base - discount, Decimal('0.00'))
    elif tipo == Promocion.Tipo.MONTO_FIJO:
        return max(base - promo.valor_descuento, Decimal('0.00'))
    # COMPRA_X_LLEVA_Y doesn't reduce the per-unit price directly.
    return None


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
