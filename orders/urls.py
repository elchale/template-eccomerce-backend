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
    AdminOrderDetailView,
    AdminOrderListView,
    AdminOrderRefundView,
    AdminOrderStatusUpdateView,
    CheckoutView,
    OrderDetailView,
    OrderListView,
)
from orders.views.analytics import DashboardView
from orders.views_payment import create_izipay_token, verify_izipay_payment, izipay_ipn

urlpatterns = [
    # Cart
    path('api/cart/', CartView.as_view(), name='cart'),
    path('api/cart/items/', AddToCartView.as_view(), name='cart-add-item'),
    path('api/cart/items/<int:pk>/', UpdateCartItemView.as_view(), name='cart-update-item'),
    path('api/cart/items/<int:pk>/delete/', RemoveCartItemView.as_view(), name='cart-remove-item'),
    path('api/cart/clear/', ClearCartView.as_view(), name='cart-clear'),
    path('api/cart/merge/', MergeCartView.as_view(), name='cart-merge'),

    # Checkout
    path('api/checkout/', CheckoutView.as_view(), name='checkout'),

    # Customer orders
    path('api/orders/', OrderListView.as_view(), name='order-list'),
    path('api/orders/<str:order_number>/', OrderDetailView.as_view(), name='order-detail'),

    # Admin orders
    path('api/admin/orders/', AdminOrderListView.as_view(), name='admin-order-list'),
    path('api/admin/orders/<int:pk>/', AdminOrderDetailView.as_view(), name='admin-order-detail'),
    path('api/admin/orders/<int:pk>/status/', AdminOrderStatusUpdateView.as_view(), name='admin-order-status-update'),
    path('api/admin/orders/<int:pk>/refund/', AdminOrderRefundView.as_view(), name='admin-order-refund'),

    # Admin dashboard
    path('api/admin/dashboard/', DashboardView.as_view(), name='admin-dashboard'),

    # Izipay payment endpoints (ADR §5)
    path('api/payments/izipay/create-token/', create_izipay_token, name='izipay-create-token'),
    path('api/payments/izipay/verify/', verify_izipay_payment, name='izipay-verify'),
    path('api/payments/izipay/ipn/', izipay_ipn, name='izipay-ipn'),
]
