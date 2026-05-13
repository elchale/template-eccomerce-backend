import logging
from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend

User = get_user_model()
logger = logging.getLogger(__name__)

"""
Backends are used to authenticate users.

The default backend to authenticate users is ModelBackend.

These need to be used in settings.AUTHENTICATION_BACKENDS.
"""

class CaseInsensitiveModelBackend(ModelBackend):
    """
    Backend that authenticates users with case-insensitive email.
    """
    def authenticate(self, request, email=None, password=None, **kwargs):
        if email is None:
            # Try to get email, or fall back to username if email isn't provided
            email = kwargs.get(User.EMAIL_FIELD) or kwargs.get('username')
            logger.debug(f"Attempting authentication with: {email}")
        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            # Hash the password even for non-existent users to prevent timing attacks
            # that could reveal whether a email exists in the database
            User().set_password(password)
        else:
            if user.check_password(password) and self.user_can_authenticate(user):
                return user


