from rest_framework import status
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from core.exceptions import BaseError

class AccountNotActive(ValidationError):
    """Raised when the user is not active."""
    pass

class MaxCaptchaSkipAttempts(Exception):
    """Raised when the user has reached the maximum number of captcha skip attempts."""
    pass


class Wrong2FATooManyTimes(BaseError):
    default_detail = _('Wrong input 2fa code too many times. Please login again.')
    default_code = 'wrong_2fa_many_times'


class TwoFAFailed(BaseError):
    status_code = status.HTTP_403_FORBIDDEN
    default_detail = _('You do not have permission to perform this action.')
    default_code = '2fa_failed'
