from django.urls import path, include
from rest_framework.routers import DefaultRouter

from coupons.views.coupons import CouponValidateView, AdminCouponViewSet

router = DefaultRouter()
router.register('admin/coupons', AdminCouponViewSet, basename='admin-coupons')

urlpatterns = [
    path('api/coupons/validate/', CouponValidateView.as_view(), name='coupon-validate'),
    path('api/', include(router.urls)),
]
