"""GDPR data export endpoint."""
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

User = get_user_model()


class UserDataExportView(APIView):
    """GET /api/users/me/export/

    Returns a JSON payload containing all personal data for the requesting
    user.  Requires the ``X-Confirm-Password`` header for re-authentication.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        confirm_password = request.META.get('HTTP_X_CONFIRM_PASSWORD', '')
        if not confirm_password:
            return Response(
                {'message': 'Se requiere X-Confirm-Password para exportar datos.', 'type': 'confirmation_required', 'field_errors': {}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = request.user
        if not user.check_password(confirm_password):
            return Response(
                {'message': 'Contraseña incorrecta.', 'type': 'invalid_password', 'field_errors': {}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Build the export payload
        from users.models import UserAddress
        from orders.models import Order
        from products.models import Review, Wishlist

        profile_data = {}
        if hasattr(user, 'profile'):
            p = user.profile
            profile_data = {
                'actions_freezed_till': str(p.actions_freezed_till) if p.actions_freezed_till else None,
            }

        addresses = list(
            UserAddress.objects.filter(user=user).values(
                'id', 'label', 'recipient_name', 'phone', 'street', 'street_2',
                'city', 'state', 'postal_code', 'country',
                'is_default_shipping', 'is_default_billing',
            )
        )

        orders = []
        for order in Order.objects.filter(user=user).prefetch_related('items').order_by('-created'):
            orders.append({
                'order_number': order.order_number,
                'status': order.status,
                'total': str(order.total),
                'created': str(order.created),
                'items': [
                    {
                        'product_name': item.product_name,
                        'quantity': item.quantity,
                        'price': str(item.price),
                    }
                    for item in order.items.all()
                ],
            })

        reviews = list(
            Review.objects.filter(user=user).values('id', 'product_id', 'rating', 'title', 'comment', 'created')
        )

        wishlist = list(
            Wishlist.objects.filter(user=user).values('product_id', 'created')
        )

        payload = {
            'user': {
                'id': user.pk,
                'email': user.email,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'username': user.username,
                'date_joined': str(user.date_joined),
            },
            'profile': profile_data,
            'addresses': addresses,
            'orders': orders,
            'reviews': reviews,
            'wishlist': wishlist,
        }

        return Response(payload, status=status.HTTP_200_OK)
