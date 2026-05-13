from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from orders.models import Cart, CartItem
from orders.serializers.cart import (
    AddToCartSerializer,
    CartSerializer,
    UpdateCartItemSerializer,
)
from products.models import Product, ProductVariant


def _get_cart_with_prefetch(cart):
    """Re-fetch a Cart with all relations needed by CartSerializer to avoid N+1."""
    return (
        Cart.objects
        .prefetch_related(
            'items__product__images',
            'items__variant__options__variant_type',
        )
        .get(pk=cart.pk)
    )


class CartView(APIView):
    """GET - Retrieve the current user's cart, auto-create if it doesn't exist."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        cart, _ = Cart.objects.get_or_create(user=request.user)
        cart = _get_cart_with_prefetch(cart)
        serializer = CartSerializer(cart)
        return Response(serializer.data)


class AddToCartView(APIView):
    """POST - Add an item to the cart. Updates quantity if item already exists."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = AddToCartSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        cart, _ = Cart.objects.get_or_create(user=request.user)
        product = Product.objects.get(pk=serializer.validated_data['product_id'])
        variant_id = serializer.validated_data.get('variant_id')
        variant = None
        if variant_id:
            variant = ProductVariant.objects.get(pk=variant_id)

        quantity = serializer.validated_data['quantity']

        cart_item, created = CartItem.objects.get_or_create(
            cart=cart,
            product=product,
            variant=variant,
            defaults={'quantity': quantity},
        )

        if not created:
            new_quantity = cart_item.quantity + quantity
            # Validate against stock
            available = variant.stock if variant else product.stock
            if new_quantity > available:
                return Response(
                    {'detail': f'Only {available} units available. You already have {cart_item.quantity} in your cart.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            cart_item.quantity = new_quantity
            cart_item.save()

        cart = _get_cart_with_prefetch(cart)
        cart_serializer = CartSerializer(cart)
        return Response(
            cart_serializer.data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class UpdateCartItemView(APIView):
    """PATCH - Update the quantity of a cart item."""

    permission_classes = [IsAuthenticated]

    def patch(self, request, pk):
        try:
            cart_item = CartItem.objects.select_related(
                'cart', 'product', 'variant'
            ).get(pk=pk, cart__user=request.user)
        except CartItem.DoesNotExist:
            return Response(
                {'detail': 'Cart item not found.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = UpdateCartItemSerializer(
            data=request.data,
            context={'cart_item': cart_item},
        )
        serializer.is_valid(raise_exception=True)

        cart_item.quantity = serializer.validated_data['quantity']
        cart_item.save()

        refreshed_cart = _get_cart_with_prefetch(cart_item.cart)
        cart_serializer = CartSerializer(refreshed_cart)
        return Response(cart_serializer.data)


class RemoveCartItemView(APIView):
    """DELETE - Remove a single item from the cart."""

    permission_classes = [IsAuthenticated]

    def delete(self, request, pk):
        try:
            cart_item = CartItem.objects.get(pk=pk, cart__user=request.user)
        except CartItem.DoesNotExist:
            return Response(
                {'detail': 'Cart item not found.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        cart = cart_item.cart
        cart_item.delete()

        cart = _get_cart_with_prefetch(cart)
        cart_serializer = CartSerializer(cart)
        return Response(cart_serializer.data)


class ClearCartView(APIView):
    """DELETE - Remove all items from the cart."""

    permission_classes = [IsAuthenticated]

    def delete(self, request):
        try:
            cart = Cart.objects.get(user=request.user)
        except Cart.DoesNotExist:
            return Response(
                {'detail': 'Cart not found.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        cart.items.all().delete()

        cart = _get_cart_with_prefetch(cart)
        cart_serializer = CartSerializer(cart)
        return Response(cart_serializer.data)
