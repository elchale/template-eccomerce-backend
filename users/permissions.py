"""Custom DRF permission classes for the users app."""
from django.conf import settings
from rest_framework.permissions import BasePermission


def _user_has_verified_otp(user) -> bool:
    """Return True if the user has a verified OTP device on this session."""
    try:
        from django_otp import user_has_device
        # django_otp marks the user when they pass OTP verification
        return bool(getattr(user, 'otp_device', None) or user_has_device(user))
    except Exception:
        return False


class IsStaffAndOTPVerified(BasePermission):
    """Allow access to staff users.

    When REQUIRE_OTP_FOR_ADMIN_API=True (opt-in), the user must additionally
    have a verified OTP device on the current session.  The default is False
    (OTP not required) so existing deployments are not broken by this setting.
    """

    message = 'Staff access required.'

    def has_permission(self, request, view) -> bool:
        if not request.user or not request.user.is_authenticated:
            return False
        if not request.user.is_staff:
            return False
        require_otp = getattr(settings, 'REQUIRE_OTP_FOR_ADMIN_API', False)
        if require_otp and not _user_has_verified_otp(request.user):
            self.message = 'OTP verification required.'
            return False
        return True
