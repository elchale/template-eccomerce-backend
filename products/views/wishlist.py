from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from products.models import Wishlist
from products.serializers.wishlist import WishlistSerializer, WishlistToggleSerializer


class WishlistListView(generics.ListAPIView):
    """
    Authenticated user's wishlist.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = WishlistSerializer

    def get_queryset(self):
        return (
            Wishlist.objects
            .filter(user=self.request.user)
            .select_related('product__category')
            .prefetch_related('product__images')
            .order_by('-created')
        )


class WishlistToggleView(APIView):
    """
    POST toggles a product in the user's wishlist.
    If the product is already in the wishlist, it is removed.
    If not, it is added.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = WishlistToggleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        product = serializer.validated_data['product']
        user = request.user

        wishlist_item, created = Wishlist.objects.get_or_create(
            user=user, product=product
        )

        if not created:
            wishlist_item.delete()
            return Response(
                {'detail': 'Product removed from wishlist.', 'added': False},
                status=status.HTTP_200_OK,
            )

        return Response(
            {'detail': 'Product added to wishlist.', 'added': True},
            status=status.HTTP_201_CREATED,
        )
