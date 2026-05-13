"""User-related models: Profile, LoginHistory, UserAddress."""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import models, transaction
from django.utils import timezone
from django_countries.fields import CountryField

from core.models import BaseModel, UserMixinModel

User = get_user_model()


class Profile(BaseModel):
    """User profile with additional information and security settings."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')

    # Security settings
    actions_freezed_till = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'User Profile'
        verbose_name_plural = 'User Profiles'

    def __str__(self):
        return f"{self.user.email} Profile"

    def set_actions_freeze(self, hours=24):
        """Freeze user actions for the given number of hours."""
        self.actions_freezed_till = timezone.now() + timedelta(hours=hours)
        self.save(update_fields=['actions_freezed_till'])

    def is_actions_frozen(self):
        """Return True if user actions are currently frozen."""
        if not self.actions_freezed_till:
            return False
        return timezone.now() < self.actions_freezed_till


class LoginHistory(UserMixinModel):
    """Tracks user login attempts with IP and user agent information."""

    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, blank=True)
    timestamp = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = 'Login history'
        verbose_name_plural = 'Login histories'
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.user.email} - {self.ip} - {self.timestamp}"


class UserAddress(BaseModel, UserMixinModel):
    """Saved shipping / billing address for a user.

    At most one address per user may be marked as default_shipping, and at
    most one as default_billing.  save() enforces this atomically.
    """

    label = models.CharField(max_length=100, blank=True, help_text='E.g. "Casa", "Oficina"')
    recipient_name = models.CharField(max_length=255)
    phone = models.CharField(max_length=30, blank=True)
    street = models.CharField(max_length=255)
    street_2 = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100, blank=True)
    postal_code = models.CharField(max_length=20, blank=True)
    country = CountryField(default='PE')
    is_default_shipping = models.BooleanField(default=False)
    is_default_billing = models.BooleanField(default=False)

    class Meta:
        verbose_name = 'User Address'
        verbose_name_plural = 'User Addresses'
        ordering = ['-is_default_shipping', '-created']

    def __str__(self):
        return f"{self.recipient_name} — {self.street}, {self.city} ({self.user})"

    def save(self, *args, **kwargs):
        """Atomically enforce single-default-per-user invariants."""
        with transaction.atomic():
            if self.is_default_shipping:
                UserAddress.objects.filter(
                    user=self.user, is_default_shipping=True
                ).exclude(pk=self.pk).update(is_default_shipping=False)
            if self.is_default_billing:
                UserAddress.objects.filter(
                    user=self.user, is_default_billing=True
                ).exclude(pk=self.pk).update(is_default_billing=False)
            super().save(*args, **kwargs)
