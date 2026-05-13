from django.contrib import admin

from orders.models import Cart, CartItem, IpnEvent, Order, OrderItem, OrderStatusHistory, Payment


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = [
        'product',
        'variant',
        'product_name',
        'variant_info',
        'price',
        'quantity',
        'image_url',
    ]


class OrderStatusHistoryInline(admin.TabularInline):
    model = OrderStatusHistory
    extra = 0
    readonly_fields = ['old_status', 'new_status', 'note', 'changed_by', 'created']


class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 0
    readonly_fields = ['method', 'amount', 'status', 'transaction_id', 'raw_response', 'created']
    can_delete = False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ['order_number', 'user', 'status', 'payment_status', 'total', 'created']
    list_filter = ['status', 'payment_status', 'created']
    search_fields = ['order_number', 'user__email', 'email']
    readonly_fields = [
        'uuid', 'order_number', 'subtotal', 'discount_amount', 'total',
        'payment_status', 'payment_method', 'izipay_transaction_id',
        'created', 'updated',
    ]
    inlines = [OrderItemInline, OrderStatusHistoryInline, PaymentInline]
    ordering = ['-created']


class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0
    readonly_fields = ['product', 'variant', 'quantity']


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ['user', 'created', 'updated']
    search_fields = ['user__email']
    readonly_fields = ['created', 'updated']
    inlines = [CartItemInline]


@admin.register(CartItem)
class CartItemAdmin(admin.ModelAdmin):
    list_display = ['cart', 'product', 'variant', 'quantity', 'created']
    list_filter = ['created']
    search_fields = ['product__name', 'cart__user__email']


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    """Read-only view of payment records for forensics."""
    list_display = ['id', 'order', 'method', 'amount', 'status', 'transaction_id', 'created']
    list_filter = ['status', 'method', 'created']
    search_fields = ['order__order_number', 'transaction_id']
    readonly_fields = ['order', 'method', 'amount', 'status', 'transaction_id', 'raw_response', 'created', 'updated']
    ordering = ['-created']

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(IpnEvent)
class IpnEventAdmin(admin.ModelAdmin):
    """Read-only audit ledger of all IPN events received from Izipay (BP5)."""
    list_display = [
        'id', 'order_number', 'processed_outcome', 'order_status',
        'source_ip', 'kr_hash_prefix', 'created',
    ]
    list_filter = ['processed_outcome', 'order_status', 'created']
    search_fields = ['order_number', 'source_ip', 'kr_hash_prefix']
    readonly_fields = [
        'source_ip', 'kr_hash_prefix', 'order_number', 'order_status',
        'processed_outcome', 'raw_body', 'error_detail', 'created', 'updated',
    ]
    ordering = ['-created']

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
