from rest_framework import serializers

from orders.models import Order, OrderItem, OrderStatusHistory


class OrderItemSerializer(serializers.ModelSerializer):
    line_total = serializers.SerializerMethodField()

    class Meta:
        model = OrderItem
        fields = [
            'id',
            'product',
            'variant',
            'product_name',
            'variant_info',
            'price',
            'quantity',
            'image_url',
            'line_total',
        ]

    def get_line_total(self, obj):
        return str(obj.price * obj.quantity)


class OrderStatusHistorySerializer(serializers.ModelSerializer):
    changed_by_email = serializers.EmailField(
        source='changed_by.email', read_only=True, default=''
    )

    class Meta:
        model = OrderStatusHistory
        fields = [
            'id',
            'old_status',
            'new_status',
            'note',
            'changed_by_email',
            'created',
        ]


class OrderListSerializer(serializers.ModelSerializer):
    item_count = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            'id',
            'uuid',
            'order_number',
            'status',
            'payment_status',
            'subtotal',
            'discount_amount',
            'total',
            'item_count',
            'created',
            'updated',
        ]
        read_only_fields = ['uuid', 'payment_status']

    def get_item_count(self, obj):
        # Use len() on prefetched items instead of a separate .count() query.
        return len(obj.items.all())


class OrderDetailSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    status_history = OrderStatusHistorySerializer(many=True, read_only=True)
    coupon_code = serializers.CharField(
        source='coupon.code', read_only=True, default=''
    )

    class Meta:
        model = Order
        fields = [
            'id',
            'uuid',
            'order_number',
            'status',
            'payment_status',
            'payment_method',
            'izipay_transaction_id',
            'subtotal',
            'discount_amount',
            'total',
            'shipping_address',
            'billing_address',
            'email',
            'phone',
            'notes',
            'coupon_code',
            'items',
            'status_history',
            'created',
            'updated',
        ]
        read_only_fields = ['uuid', 'payment_status', 'payment_method', 'izipay_transaction_id']


class CheckoutSerializer(serializers.Serializer):
    shipping_address = serializers.CharField(max_length=1000)
    billing_address = serializers.CharField(max_length=1000, required=False, allow_blank=True)
    email = serializers.EmailField()
    phone = serializers.CharField(max_length=20, required=False, allow_blank=True)
    notes = serializers.CharField(max_length=500, required=False, allow_blank=True)
    coupon_code = serializers.CharField(required=False, allow_blank=True)


class AdminOrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    status_history = OrderStatusHistorySerializer(many=True, read_only=True)
    user_email = serializers.EmailField(
        source='user.email', read_only=True, default=''
    )
    coupon_code = serializers.CharField(
        source='coupon.code', read_only=True, default=''
    )
    item_count = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            'id',
            'uuid',
            'order_number',
            'user',
            'user_email',
            'status',
            'payment_status',
            'payment_method',
            'izipay_transaction_id',
            'subtotal',
            'discount_amount',
            'total',
            'shipping_address',
            'billing_address',
            'email',
            'phone',
            'notes',
            'coupon_code',
            'items',
            'status_history',
            'item_count',
            'created',
            'updated',
        ]
        read_only_fields = ['uuid', 'payment_status', 'payment_method', 'izipay_transaction_id']

    def get_item_count(self, obj):
        # Use len() on prefetched items instead of a separate .count() query.
        return len(obj.items.all())


class AdminOrderStatusUpdateSerializer(serializers.Serializer):
    new_status = serializers.ChoiceField(choices=Order.Status.choices)
    note = serializers.CharField(required=False, allow_blank=True, default='')


class DashboardSerializer(serializers.Serializer):
    total_revenue = serializers.DecimalField(max_digits=12, decimal_places=2)
    order_counts = serializers.DictField()
    top_products = serializers.ListField()
    revenue_by_day = serializers.ListField()
    recent_orders = serializers.ListField()
    new_customers_count = serializers.IntegerField()
