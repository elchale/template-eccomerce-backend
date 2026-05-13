from rest_framework import serializers

from products.models import Review


class ReviewSerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(source='user.email', read_only=True)
    user_name = serializers.SerializerMethodField()

    class Meta:
        model = Review
        fields = [
            'id',
            'user',
            'user_email',
            'user_name',
            'product',
            'rating',
            'title',
            'comment',
            'is_verified_purchase',
            'created',
            'updated',
        ]
        read_only_fields = [
            'id',
            'user',
            'is_verified_purchase',
            'created',
            'updated',
        ]

    def get_user_name(self, obj):
        if obj.user.first_name or obj.user.last_name:
            return f"{obj.user.first_name} {obj.user.last_name}".strip()
        return obj.user.email


class ReviewCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Review
        fields = [
            'id',
            'product',
            'rating',
            'title',
            'comment',
        ]
        read_only_fields = ['id']

    def validate_rating(self, value):
        if value < 1 or value > 5:
            raise serializers.ValidationError(
                'Rating must be between 1 and 5.'
            )
        return value

    def validate(self, attrs):
        user = self.context['request'].user
        product = attrs.get('product')

        # Check uniqueness: one review per user per product
        if Review.objects.filter(user=user, product=product).exists():
            raise serializers.ValidationError(
                {'product': 'You have already reviewed this product.'}
            )

        return attrs

    def create(self, validated_data):
        user = self.context['request'].user
        validated_data['user'] = user

        # Check if user has a delivered order containing this product
        from orders.models import Order, OrderItem
        is_verified = OrderItem.objects.filter(
            order__user=user,
            order__status=Order.Status.DELIVERED,
            product=validated_data['product'],
        ).exists()
        validated_data['is_verified_purchase'] = is_verified

        return super().create(validated_data)
