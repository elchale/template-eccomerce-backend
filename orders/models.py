"""Order domain models.

Design notes:
- Order is an immutable snapshot: OrderItem denormalises product name + price.
- Cart supports both authenticated users and anonymous sessions (guest checkout).
- IpnEvent is a write-only ledger for forensic reconciliation.
- Refund tracks refund requests independently of the payment gateway.
"""
import uuid
from datetime import date

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import IntegrityError, models
from django.db.models import Q

from core.models import BaseModel, UserMixinModel


class Cart(BaseModel):
    """Shopping cart — supports both auth users and anonymous sessions.

    Constraints:
      - At most one cart per authenticated user (unique_cart_per_user).
      - At most one cart per session key (unique_cart_per_session).
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='carts',
    )
    session_key = models.CharField(max_length=40, blank=True, default='')

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['user'],
                condition=Q(user__isnull=False),
                name='unique_cart_per_user',
            ),
            models.UniqueConstraint(
                fields=['session_key'],
                condition=~Q(session_key=''),
                name='unique_cart_per_session',
            ),
        ]

    def __str__(self):
        if self.user:
            return f"Cart - {self.user}"
        return f"Cart - session:{self.session_key}"


class CartItem(BaseModel):
    cart = models.ForeignKey(
        Cart,
        on_delete=models.CASCADE,
        related_name='items',
    )
    product = models.ForeignKey(
        'products.Product',
        on_delete=models.CASCADE,
    )
    variant = models.ForeignKey(
        'products.ProductVariant',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    quantity = models.PositiveIntegerField(default=1)

    class Meta:
        unique_together = ('cart', 'product', 'variant')

    def __str__(self):
        return f"{self.product.name} x{self.quantity}"


class Order(BaseModel, UserMixinModel):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        CONFIRMED = 'confirmed', 'Confirmed'
        PROCESSING = 'processing', 'Processing'
        SHIPPED = 'shipped', 'Shipped'
        DELIVERED = 'delivered', 'Delivered'
        CANCELLED = 'cancelled', 'Cancelled'
        REFUNDED = 'refunded', 'Refunded'

    PAYMENT_STATUS_CHOICES = [
        ('unpaid', 'Sin pagar'),
        ('paid', 'Pagado'),
        ('refunded', 'Reembolsado'),
    ]

    # UUID for IPN routing and external references
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)

    order_number = models.CharField(max_length=50, unique=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    # Phase 2: tax + currency + shipping + idempotency
    currency_code = models.CharField(max_length=3, default='PEN', db_index=True)
    tax_amount = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        validators=[MinValueValidator(0)],
    )
    tax_rate = models.DecimalField(
        max_digits=5, decimal_places=4, default=0,
        help_text='0.0000–1.0000 fraction, e.g. 0.18 for 18% IGV',
    )
    shipping_amount = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        validators=[MinValueValidator(0)],
    )
    idempotency_key = models.CharField(max_length=64, blank=True, default='')

    shipping_address = models.TextField(blank=True)
    billing_address = models.TextField(blank=True)
    notes = models.TextField(max_length=2000, blank=True)
    coupon = models.ForeignKey(
        'coupons.Coupon',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_index=True,
    )
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=20, blank=True)

    # Payment fields (added for Izipay integration)
    payment_status = models.CharField(
        max_length=20,
        choices=PAYMENT_STATUS_CHOICES,
        default='unpaid',
        db_index=True,
    )
    payment_method = models.CharField(max_length=20, default='', blank=True)
    izipay_transaction_id = models.CharField(max_length=100, default='', blank=True)
    izipay_form_token_created_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created']
        indexes = [
            models.Index(fields=['user', '-created'], name='order_user_created_idx'),
            models.Index(fields=['status', '-created'], name='order_status_created_idx'),
            models.Index(fields=['email'], name='order_email_idx'),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'idempotency_key'],
                condition=Q(idempotency_key__gt=''),
                name='order_idempo_user',
            ),
        ]

    def __str__(self):
        return f"Order {self.order_number}"

    def save(self, *args, **kwargs):
        if not self.order_number:
            today = date.today().strftime('%Y%m%d')
            for _ in range(5):
                random_part = uuid.uuid4().hex[:4].upper()
                candidate = f"QLCA-{today}-{random_part}"
                if not Order.objects.filter(order_number=candidate).exists():
                    self.order_number = candidate
                    break
            else:
                raise IntegrityError("Could not generate unique order_number after 5 attempts")
        super().save(*args, **kwargs)


class OrderItem(BaseModel):
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name='items',
    )
    product = models.ForeignKey(
        'products.Product',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    variant = models.ForeignKey(
        'products.ProductVariant',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    product_name = models.CharField(max_length=255)
    variant_info = models.CharField(max_length=255, blank=True)
    price = models.DecimalField(
        max_digits=10, decimal_places=2,
        validators=[MinValueValidator(0)],
    )
    quantity = models.PositiveIntegerField(
        default=1,
        validators=[MinValueValidator(1)],
    )
    image_url = models.URLField(blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['product'], name='orderitem_product_idx'),
        ]

    def __str__(self):
        return f"{self.product_name} x{self.quantity}"


class OrderStatusHistory(BaseModel):
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name='status_history',
    )
    old_status = models.CharField(max_length=20, choices=Order.Status.choices)
    new_status = models.CharField(max_length=20, choices=Order.Status.choices)
    note = models.TextField(max_length=2000, blank=True)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ['-created']
        verbose_name_plural = 'order status histories'

    def __str__(self):
        return f"Order {self.order.order_number}: {self.old_status} → {self.new_status}"


class Refund(BaseModel):
    """Tracks refund requests for orders.

    ``external_refund_id`` is reserved for Izipay's refund handle once
    gateway-side refunds are implemented in a later pass.
    """

    class RefundStatus(models.TextChoices):
        PENDING = 'pending', 'Pendiente'
        APPROVED = 'approved', 'Aprobado'
        REJECTED = 'rejected', 'Rechazado'
        PROCESSED = 'processed', 'Procesado'

    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name='refunds',
    )
    amount = models.DecimalField(
        max_digits=10, decimal_places=2,
        validators=[MinValueValidator(0)],
    )
    reason = models.TextField(blank=True)
    status = models.CharField(
        max_length=20,
        choices=RefundStatus.choices,
        default=RefundStatus.PENDING,
        db_index=True,
    )
    external_refund_id = models.CharField(max_length=100, blank=True)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='refund_requests',
    )
    processed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+',
    )

    class Meta:
        ordering = ['-created']

    def __str__(self):
        return f"Refund {self.id} for {self.order.order_number} [{self.status}]"


class Payment(BaseModel):
    """Records a verified payment transaction from Izipay.

    BP7: Only statuses are 'verified' and 'refunded'.
    We never write 'pending' payments — IPN is the sole source of truth.
    """
    METHOD_CHOICES = [
        ('izipay', 'Izipay (tarjeta)'),
        ('yape', 'Yape (vía Izipay)'),
        ('transfer', 'Transferencia'),
    ]
    STATUS_CHOICES = [
        ('verified', 'Verificado'),
        ('refunded', 'Reembolsado'),
    ]

    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name='payments',
    )
    method = models.CharField(max_length=20, choices=METHOD_CHOICES)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='verified')
    transaction_id = models.CharField(max_length=100, db_index=True)
    raw_response = models.JSONField(default=dict)

    class Meta:
        ordering = ['-created']
        indexes = [
            models.Index(fields=['order', '-created'], name='payment_order_created_idx'),
        ]
        verbose_name = 'Payment'
        verbose_name_plural = 'Payments'

    def __str__(self):
        return f"Payment {self.id} for {self.order.order_number} [{self.get_status_display()}]"


class EmailLog(BaseModel):
    """Persistent audit log for every order email dispatched.

    One row per logical email event. Re-renders on retry from live
    template + order data — the body is NOT stored.
    """

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pendiente'
        RETRYING = 'retrying', 'Reintentando'
        CONFIRMED = 'confirmed', 'Confirmado'
        FAILED = 'failed', 'Fallido'

    class EmailType(models.TextChoices):
        CUSTOMER_PAYMENT_RECEIVED = 'customer_payment_received', 'Pago confirmado — cliente'
        CUSTOMER_STATUS_UPDATE = 'customer_status_update', 'Actualización de estado — cliente'
        CUSTOMER_REFUND = 'customer_refund', 'Reembolso procesado — cliente'
        ADMIN_NEW_PAID_ORDER = 'admin_new_paid_order', 'Nuevo pedido pagado — administrador'
        ADMIN_STATUS_UPDATE = 'admin_status_update', 'Actualización de estado — administrador'
        ADMIN_AMOUNT_MISMATCH = 'admin_amount_mismatch', 'Alerta de monto incorrecto — administrador'

    email_type = models.CharField(
        max_length=50,
        choices=EmailType.choices,
        db_index=True,
    )
    template_name = models.CharField(max_length=255)
    subject = models.CharField(max_length=255)
    recipient_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='email_logs',
    )
    recipient_email = models.EmailField()
    order = models.ForeignKey(
        'Order',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='email_logs',
        db_index=True,
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    task_name = models.CharField(max_length=255)
    task_args = models.JSONField(default=dict)
    error_message = models.TextField(blank=True, default='')
    attempts = models.PositiveSmallIntegerField(default=0)
    sent_at = models.DateTimeField(null=True, blank=True)
    last_attempt_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created']
        indexes = [
            models.Index(fields=['status'], name='emaillog_status_idx'),
            models.Index(fields=['email_type', 'status'], name='emaillog_type_status_idx'),
        ]
        verbose_name = 'Email Log'
        verbose_name_plural = 'Email Logs'

    def __str__(self):
        return f"EmailLog {self.id}: {self.email_type} → {self.recipient_email} [{self.status}]"


class IpnEvent(BaseModel):
    """Write-only audit ledger for every Izipay IPN received.

    BP5: Forensics + replay debugging. Every IPN call creates one row.
    """
    OUTCOME_CHOICES = [
        ('paid', 'Paid'),
        ('refunded', 'Refunded'),
        ('cancelled', 'Cancelled'),
        ('unpaid', 'Unpaid'),
        ('duplicate', 'Duplicate'),
        ('no_order', 'No Order'),
        ('bad_amount', 'Bad Amount'),
        ('bad_signature', 'Bad Signature'),
        ('no_op', 'No Operation'),
    ]

    source_ip = models.CharField(max_length=45)
    kr_hash_prefix = models.CharField(max_length=8)  # First 8 hex chars for forensics
    order_number = models.CharField(max_length=50, db_index=True)
    order_status = models.CharField(max_length=20, blank=True)  # As received from Izipay
    processed_outcome = models.CharField(max_length=20, choices=OUTCOME_CHOICES, db_index=True)
    raw_body = models.TextField()  # Truncated to 4096 chars in application logic
    error_detail = models.TextField(blank=True)

    class Meta:
        ordering = ['-created']
        indexes = [
            models.Index(
                fields=['order_number', '-created'],
                name='ipnevent_order_created_idx',
            ),
            models.Index(
                fields=['processed_outcome', '-created'],
                name='ipnevent_outcome_created_idx',
            ),
        ]
        verbose_name = 'IPN Event'
        verbose_name_plural = 'IPN Events'

    def __str__(self):
        return f"IpnEvent {self.id}: {self.order_number} [{self.processed_outcome}] @ {self.created}"
