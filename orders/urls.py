from django.conf import settings
from django.urls import path

from orders.views.cart import (
    AddToCartView,
    CartView,
    ClearCartView,
    MergeCartView,
    RemoveCartItemView,
    UpdateCartItemView,
)
from orders.views.orders import (
    AdminEmailLogListView,
    AdminEmailLogRetryView,
    AdminOrderDetailView,
    AdminOrderListView,
    AdminOrderRefundView,
    AdminOrderStatusUpdateView,
    OrderDetailView,
    OrderListView,
)
from orders.views.analytics import DashboardView
from orders.views_payment import create_izipay_token, verify_izipay_payment, izipay_ipn
from orders.views_culqi import create_culqi_charge, create_culqi_order, culqi_webhook
from orders.views_mp import create_mp_payment
from orders.views_checkout import checkout_pay, checkout_session_status

urlpatterns = [
    # Cart
    path('api/cart/', CartView.as_view(), name='cart'),
    path('api/cart/items/', AddToCartView.as_view(), name='cart-add-item'),
    path('api/cart/items/<int:pk>/', UpdateCartItemView.as_view(), name='cart-update-item'),
    path('api/cart/items/<int:pk>/delete/', RemoveCartItemView.as_view(), name='cart-remove-item'),
    path('api/cart/clear/', ClearCartView.as_view(), name='cart-clear'),
    path('api/cart/merge/', MergeCartView.as_view(), name='cart-merge'),

    # Checkout — order-on-payment (MP only). The Order is created ONLY when
    # the payment is confirmed; the cart is the durable pre-order state.
    path('api/checkout/pay/', checkout_pay, name='checkout-pay'),
    path(
        'api/checkout/session/<uuid:session_uuid>/status/',
        checkout_session_status,
        name='checkout-session-status',
    ),

    # Customer orders
    path('api/orders/', OrderListView.as_view(), name='order-list'),
    path('api/orders/<str:order_number>/', OrderDetailView.as_view(), name='order-detail'),

    # Admin orders
    path('api/admin/orders/', AdminOrderListView.as_view(), name='admin-order-list'),
    path('api/admin/orders/<int:pk>/', AdminOrderDetailView.as_view(), name='admin-order-detail'),
    path('api/admin/orders/<int:pk>/status/', AdminOrderStatusUpdateView.as_view(), name='admin-order-status-update'),
    path('api/admin/orders/<int:pk>/refund/', AdminOrderRefundView.as_view(), name='admin-order-refund'),

    # Admin email logs
    path('api/admin/email-logs/', AdminEmailLogListView.as_view(), name='admin-email-log-list'),
    path('api/admin/email-logs/<int:pk>/retry/', AdminEmailLogRetryView.as_view(), name='admin-email-log-retry'),

    # Admin dashboard
    path('api/admin/dashboard/', DashboardView.as_view(), name='admin-dashboard'),

    # Mercado Pago payment endpoints (ACTIVE gateway, see settings.PAYMENT_GATEWAY).
    # The MP webhook is registered at the project root as `/pay` in backend/urls.py.
    path('api/payments/mercadopago/process/', create_mp_payment, name='mercadopago-process'),

    # Culqi payment endpoints (DORMANT — kept for fallback, see settings.PAYMENT_GATEWAY)
    path('api/payments/culqi/charge/', create_culqi_charge, name='culqi-charge'),
    path('api/payments/culqi/order/', create_culqi_order, name='culqi-order'),
    # Webhook path carries an unguessable secret slug — keep it in sync with
    # the URL registered in CulqiPanel → Eventos → Webhooks.
    path(
        f'api/payments/culqi/webhook-{settings.CULQI_WEBHOOK_PATH_SECRET}/',
        culqi_webhook,
        name='culqi-webhook',
    ),

    # Izipay payment endpoints (DORMANT — kept for fallback, see settings.PAYMENT_GATEWAY)
    path('api/payments/izipay/create-token/', create_izipay_token, name='izipay-create-token'),
    path('api/payments/izipay/verify/', verify_izipay_payment, name='izipay-verify'),
    path('api/payments/izipay/ipn/', izipay_ipn, name='izipay-ipn'),
]
