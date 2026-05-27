from django.contrib import admin

from orders.models import (
    Cart,
    CartItem,
    CheckoutSession,
    EmailLog,
    IpnEvent,
    Order,
    OrderItem,
    OrderStatusHistory,
    Payment,
)


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
        'culqi_charge_id', 'culqi_order_id', 'mp_payment_id',
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


@admin.register(EmailLog)
class EmailLogAdmin(admin.ModelAdmin):
    """Read-mostly audit log of all dispatched order emails."""
    list_display = [
        'id', 'email_type', 'get_email_type_display_col', 'recipient_email',
        'status', 'attempts', 'created',
    ]
    list_filter = ['status', 'email_type', 'created']
    search_fields = ['recipient_email', 'subject', 'order__order_number']
    readonly_fields = [
        'email_type', 'template_name', 'subject', 'recipient_user', 'recipient_email',
        'order', 'status', 'task_name', 'task_args', 'error_message',
        'attempts', 'sent_at', 'last_attempt_at', 'created', 'updated',
    ]
    ordering = ['-created']

    @admin.display(description='Objetivo')
    def get_email_type_display_col(self, obj):
        return obj.get_email_type_display()

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(IpnEvent)
class IpnEventAdmin(admin.ModelAdmin):
    """Read-only audit ledger of all IPN / webhook events received (BP5).

    Gateway-agnostic — records Mercado Pago (active), Culqi (dormant) and
    Izipay (dormant) events.
    """
    list_display = [
        'id', 'gateway', 'order_number', 'processed_outcome', 'order_status',
        'source_ip', 'kr_hash_prefix', 'created',
    ]
    list_filter = ['gateway', 'processed_outcome', 'order_status', 'created']
    search_fields = ['order_number', 'source_ip', 'kr_hash_prefix']
    readonly_fields = [
        'gateway', 'source_ip', 'kr_hash_prefix', 'order_number', 'order_status',
        'processed_outcome', 'raw_body', 'error_detail', 'created', 'updated',
    ]
    ordering = ['-created']

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(CheckoutSession)
class CheckoutSessionAdmin(admin.ModelAdmin):
    """Read-only view of payment attempts (order-on-payment flow).

    An Order is created ONLY when a session reaches status='paid'. Useful for
    forensics on failed/abandoned attempts and stock-out refunds.
    """
    list_display = [
        'uuid', 'user', 'status', 'total', 'gateway', 'mp_payment_id',
        'order', 'created',
    ]
    list_filter = ['status', 'gateway', 'created']
    search_fields = ['uuid', 'mp_payment_id', 'email', 'user__email']
    readonly_fields = [
        'uuid', 'user', 'status', 'email', 'phone', 'shipping_address',
        'billing_address', 'notes', 'coupon', 'subtotal', 'discount_amount',
        'total', 'items', 'gateway', 'mp_payment_id', 'order', 'created', 'updated',
    ]
    ordering = ['-created']

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
