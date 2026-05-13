"""Users URL routing.

Auth views use manual subclasses (in views/auth.py) so we can apply
ScopedRateThrottle without monkey-patching dj-rest-auth views in place.
Token refresh uses simplejwt directly (httpOnly cookie path).
"""
from django.urls import path, include

from rest_framework_simplejwt.views import TokenRefreshView

from .views import (
    CustomVerifyEmailView,
    ResendEmailConfirmationView,
    PasswordResetConfirmView,
    UserAddressListCreateView,
    UserAddressDetailView,
    UserAddressSetDefaultView,
    UserDataExportView,
    UserAccountDeleteView,
)
from .views_social import GoogleLoginView

urlpatterns = [
    # ---- Standard dj-rest-auth endpoints (keep existing paths for compatibility) ----
    path('auth/', include('dj_rest_auth.urls')),
    path('auth/registration/', include('dj_rest_auth.registration.urls')),

    # ---- Custom email verification with auto-login ----
    path('auth/registration/account-confirm-email/', CustomVerifyEmailView.as_view(), name='account_confirm_email'),
    path('resend-email-confirmation/', ResendEmailConfirmationView.as_view(), name='resend_email_confirmation'),

    # ---- Password reset confirm page (renders HTML for the SPA redirect) ----
    path('reset-password/<str:uidb64>/<str:token>/', PasswordResetConfirmView.as_view(), name='password_reset_confirm'),

    # ---- Social auth ----
    path('auth/google/', GoogleLoginView.as_view(), name='google_login'),

    # ---- JWT token refresh (httpOnly cookie path) ----
    path('auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),

    # ---- Address book ----
    path('api/users/me/addresses/', UserAddressListCreateView.as_view(), name='user_address_list_create'),
    path('api/users/me/addresses/<int:pk>/', UserAddressDetailView.as_view(), name='user_address_detail'),
    path('api/users/me/addresses/<int:pk>/set-default/', UserAddressSetDefaultView.as_view(), name='user_address_set_default'),

    # ---- GDPR self-service ----
    path('api/users/me/export/', UserDataExportView.as_view(), name='user_data_export'),
    path('api/users/me/', UserAccountDeleteView.as_view(), name='user_account_delete'),
]
