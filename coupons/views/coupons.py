from rest_framework import generics, viewsets, status
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from coupons.models import Coupon
from coupons.serializers.coupons import CouponSerializer, CouponValidateSerializer


class CouponValidateView(generics.GenericAPIView):
    """
    Validate a coupon code against a cart subtotal.

    Accepts POST with `code` and `cart_subtotal`.
    Returns the coupon details and the calculated discount amount.
    """
    serializer_class = CouponValidateSerializer
    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'coupon_validate'

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class AdminCouponViewSet(viewsets.ModelViewSet):
    """
    Admin CRUD endpoints for coupon management.

    list:   GET    /api/admin/coupons/
    create: POST   /api/admin/coupons/
    read:   GET    /api/admin/coupons/{id}/
    update: PUT    /api/admin/coupons/{id}/
    patch:  PATCH  /api/admin/coupons/{id}/
    delete: DELETE /api/admin/coupons/{id}/
    """
    queryset = Coupon.objects.all()
    serializer_class = CouponSerializer
    permission_classes = [IsAdminUser]
