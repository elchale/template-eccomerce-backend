import logging

from django.contrib.auth.signals import user_logged_in
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model

from users.models import Profile

logger = logging.getLogger(__name__)

User = get_user_model()


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """Create a Profile instance when a new User is created."""
    if created:
        Profile.objects.create(user=instance)


@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    """Save the Profile instance when User is saved."""
    if hasattr(instance, 'profile'):
        instance.profile.save()


@receiver(user_logged_in)
def merge_guest_cart_on_login(sender, request, user, **kwargs):
    """Merge any anonymous session cart into the user's cart on login."""
    try:
        session_key = request.session.session_key
        if not session_key:
            return
        from orders.services.cart_merge import merge_session_cart_into_user_cart
        merge_session_cart_into_user_cart(session_key, user)
    except Exception as exc:
        logger.warning('Cart merge failed on login for user %s: %s', user.pk, exc)
