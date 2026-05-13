"""Cart merge service — merges an anonymous session cart into a user cart on login."""
import logging

from django.db import transaction

logger = logging.getLogger(__name__)


def merge_session_cart_into_user_cart(session_key: str, user) -> None:
    """Merge the guest cart identified by *session_key* into *user*'s cart.

    Duplicate product+variant combinations are resolved by summing quantities.
    If no session cart exists, this is a no-op.
    """
    from orders.models import Cart, CartItem

    if not session_key:
        return

    try:
        guest_cart = Cart.objects.get(session_key=session_key, user__isnull=True)
    except Cart.DoesNotExist:
        return

    with transaction.atomic():
        user_cart, _ = Cart.objects.get_or_create(user=user)

        for guest_item in guest_cart.items.select_related('product', 'variant'):
            existing = CartItem.objects.filter(
                cart=user_cart,
                product=guest_item.product,
                variant=guest_item.variant,
            ).first()

            if existing:
                existing.quantity += guest_item.quantity
                existing.save(update_fields=['quantity', 'updated'])
            else:
                guest_item.pk = None
                guest_item.cart = user_cart
                guest_item.save()

        guest_cart.delete()
        logger.info(
            'Merged session cart (key=%s) into user cart for user_id=%s',
            session_key, user.pk,
        )
