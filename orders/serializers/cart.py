from decimal import Decimal

from rest_framework import serializers

from orders.models import Cart, CartItem
from products.models import Product, ProductVariant


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

    def get_unit_price(self, obj):
        if obj.variant:
            return str(obj.variant.price)
        return str(obj.product.base_price)

    def get_line_total(self, obj):
        price = obj.variant.price if obj.variant else obj.product.base_price
        return str(price * obj.quantity)

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

    def get_subtotal(self, obj):
        # Use prefetched items to avoid extra queries.
        # list() materializes the prefetch cache so we never hit the DB again.
        items = list(obj.items.all())
        total = Decimal('0.00')
        for item in items:
            price = item.variant.price if item.variant else item.product.base_price
            total += price * item.quantity
        return str(total)

    def get_item_count(self, obj):
        # Use len() on the already-prefetched items queryset (never .count()).
        items = list(obj.items.all())
        return sum(item.quantity for item in items)
