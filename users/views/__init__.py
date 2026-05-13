"""Users views package."""
from .auth import CustomVerifyEmailView, PasswordResetConfirmView, ResendEmailConfirmationView
from .addresses import UserAddressDetailView, UserAddressListCreateView, UserAddressSetDefaultView
from .account_export import UserDataExportView
from .account_delete import UserAccountDeleteView

__all__ = [
    'CustomVerifyEmailView',
    'PasswordResetConfirmView',
    'ResendEmailConfirmationView',
    'UserAddressDetailView',
    'UserAddressListCreateView',
    'UserAddressSetDefaultView',
    'UserDataExportView',
    'UserAccountDeleteView',
]
