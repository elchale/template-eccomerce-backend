from decimal import Decimal

from django.utils import timezone
from rest_framework import serializers

from orders.models import Cart, CartItem
from products.models import Product, ProductVariant
from products.pricing import effective_unit_price, get_active_promo_for_product


def _fetch_active_promos():
    """Fetch currently-active promotions once, with prefetched M2M relations,
    sorted by ``-prioridad`` — mirrors products/views batch approach to avoid
    N+1 lookups when pricing a cart."""
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


class CartItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_slug = serializers.CharField(source='product.slug', read_only=True)
    product_image = serializers.SerializerMethodField()
    unit_price = serializers.SerializerMethodField()
    line_total = serializers.SerializerMethodField()
    variant_info = serializers.SerializerMethodField()

    class Meta:
        model = CartItem
        fields = [
            'id',
            'product',
            'variant',
            'product_name',
            'product_slug',
            'product_image',
            'variant_info',
            'unit_price',
            'quantity',
            'line_total',
        ]

    def get_product_image(self, obj):
        # Use prefetched images to avoid N+1 queries.
        images = list(obj.product.images.all())
        primary = next((img for img in images if img.is_primary), None)
        if primary:
            return primary.image_url
        return images[0].image_url if images else ''

    def _active_promos(self):
        """Active promos for promo resolution. Prefer the parent serializer's
        prefetched list (passed via context) so the whole cart shares one
        query; fall back to a per-instance fetch if used standalone."""
        promos = self.context.get('active_promos')
        if promos is not None:
            return promos
        if not hasattr(self, '_cached_active_promos'):
            self._cached_active_promos = _fetch_active_promos()
        return self._cached_active_promos

    def _effective_unit_price(self, obj):
        promo = get_active_promo_for_product(
            obj.product, active_promos=self._active_promos()
        )
        return effective_unit_price(obj.product, obj.variant, promo)

    def get_unit_price(self, obj):
        return str(self._effective_unit_price(obj))

    def get_line_total(self, obj):
        return str(self._effective_unit_price(obj) * obj.quantity)

    def get_variant_info(self, obj):
        if not obj.variant:
            return ''
        # Use prefetched options to avoid N+1 queries.
        options = list(obj.variant.options.all())
        return ', '.join(
            f"{opt.variant_type.name}: {opt.value}" for opt in options
        )


class AddToCartSerializer(serializers.Serializer):
    product_id = serializers.IntegerField()
    variant_id = serializers.IntegerField(required=False, allow_null=True)
    quantity = serializers.IntegerField(min_value=1, default=1)

    def validate_product_id(self, value):
        try:
            Product.objects.get(pk=value, is_active=True)
        except Product.DoesNotExist:
            raise serializers.ValidationError('Product not found or inactive.')
        return value

    def validate(self, data):
        product = Product.objects.get(pk=data['product_id'])
        variant_id = data.get('variant_id')
        quantity = data['quantity']

        if variant_id:
            try:
                variant = ProductVariant.objects.get(
                    pk=variant_id,
                    product=product,
                    is_active=True,
                )
            except ProductVariant.DoesNotExist:
                raise serializers.ValidationError(
                    {'variant_id': 'Variant not found or inactive.'}
                )
            if quantity > variant.stock:
                raise serializers.ValidationError(
                    {'quantity': f'Only {variant.stock} units available.'}
                )
        else:
            if quantity > product.stock:
                raise serializers.ValidationError(
                    {'quantity': f'Only {product.stock} units available.'}
                )

        return data


class MergeCartItemSerializer(serializers.Serializer):
    product_id = serializers.IntegerField()
    variant_id = serializers.IntegerField(required=False, allow_null=True)
    quantity = serializers.IntegerField(min_value=1)


class MergeCartSerializer(serializers.Serializer):
    items = MergeCartItemSerializer(many=True)


class UpdateCartItemSerializer(serializers.Serializer):
    quantity = serializers.IntegerField(min_value=1)

    def validate_quantity(self, value):
        cart_item = self.context.get('cart_item')
        if not cart_item:
            return value

        if cart_item.variant:
            available = cart_item.variant.stock
        else:
            available = cart_item.product.stock

        if value > available:
            raise serializers.ValidationError(
                f'Only {available} units available.'
            )
        return value


class CartSerializer(serializers.ModelSerializer):
    items = CartItemSerializer(many=True, read_only=True)
    subtotal = serializers.SerializerMethodField()
    item_count = serializers.SerializerMethodField()

    class Meta:
        model = Cart
        fields = ['id', 'items', 'subtotal', 'item_count', 'created', 'updated']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Fetch active promos ONCE for the whole cart and share the list with
        # the nested CartItemSerializer via context (avoids N+1 per item).
        if 'active_promos' not in self.context:
            self.context['active_promos'] = _fetch_active_promos()

    def get_subtotal(self, obj):
        # Use prefetched items to avoid extra queries.
        # list() materializes the prefetch cache so we never hit the DB again.
        items = list(obj.items.all())
        active_promos = self.context.get('active_promos')
        total = Decimal('0.00')
        for item in items:
            promo = get_active_promo_for_product(
                item.product, active_promos=active_promos
            )
            total += effective_unit_price(item.product, item.variant, promo) * item.quantity
        return str(total)

    def get_item_count(self, obj):
        # Use len() on the already-prefetched items queryset (never .count()).
        items = list(obj.items.all())
        return sum(item.quantity for item in items)
