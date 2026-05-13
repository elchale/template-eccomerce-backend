"""UserAddress CRUD views."""
from rest_framework import status
from rest_framework.generics import ListCreateAPIView, RetrieveUpdateDestroyAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from users.models import UserAddress
from users.serializers.address import UserAddressSerializer


class UserAddressListCreateView(ListCreateAPIView):
    """GET /api/users/me/addresses/ — list; POST — create.

    Pagination is disabled: users typically have < 10 addresses so a plain
    JSON array is simpler for the frontend to consume.
    """

    serializer_class = UserAddressSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None  # disable global pagination for this resource

    def get_queryset(self):
        return UserAddress.objects.filter(user=self.request.user).order_by('-is_default_shipping', '-created')


class UserAddressDetailView(RetrieveUpdateDestroyAPIView):
    """GET/PATCH/DELETE /api/users/me/addresses/<pk>/."""

    serializer_class = UserAddressSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ['get', 'patch', 'delete', 'head', 'options']

    def get_queryset(self):
        return UserAddress.objects.filter(user=self.request.user)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.delete()
        return Response({'message': 'Dirección eliminada.'}, status=status.HTTP_200_OK)


class UserAddressSetDefaultView(APIView):
    """POST /api/users/me/addresses/<pk>/set-default/ — set as default shipping+billing."""

    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        try:
            address = UserAddress.objects.get(pk=pk, user=request.user)
        except UserAddress.DoesNotExist:
            return Response(
                {'message': 'Dirección no encontrada.', 'type': 'not_found', 'field_errors': {}},
                status=status.HTTP_404_NOT_FOUND,
            )

        address.is_default_shipping = True
        address.is_default_billing = True
        address.save()

        serializer = UserAddressSerializer(address, context={'request': request})
        return Response(serializer.data)
