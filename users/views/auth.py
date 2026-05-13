import logging
from django.conf import settings
from django.http import Http404
from rest_framework import status
from dj_rest_auth.registration.views import VerifyEmailView
from django.views.generic import TemplateView
from rest_framework.response import Response
from django.utils.translation import gettext_lazy as _, activate as translation_activate, get_language as translation_get_language
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.views import APIView
from rest_framework.request import Request
from rest_framework.permissions import AllowAny
from django.core.cache import cache
from allauth.account.models import EmailAddress
from django.db.models import Model
from django.contrib.auth import get_user_model
from django.utils.timezone import now as timezone_now

from users.cache_keys import RESEND_VERIFICATION_TOKEN_CACHE_KEY
from users.serializers.auth import UserSerializer

logger = logging.getLogger(__name__)

User: Model = get_user_model()

class CustomVerifyEmailView(VerifyEmailView):
    """
    Expands the original dj_rest_auth VerifyEmailView to:
    1. Verify the email using the provided key.
    2. Generate and return authentication tokens for automatic login.
    3. Return user data matching the login endpoint response format.
    """
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        self.kwargs['key'] = serializer.validated_data['key']

        try:
            confirmation = self.get_object()
        except Http404:
            return Response({'detail': _('Invalid confirmation key.')}, status=status.HTTP_404_NOT_FOUND)

        confirmation.confirm(self.request)

        user = confirmation.email_address.user

        if not user.is_active:
            return Response({'detail': _('User account is inactive.')}, status=status.HTTP_400_BAD_REQUEST)

        # Generate JWT tokens
        refresh = RefreshToken.for_user(user)
        access_token_str = str(refresh.access_token)
        refresh_token_str = str(refresh)

        # Calculate expiration times
        access_expiration = timezone_now() + settings.SIMPLE_JWT['ACCESS_TOKEN_LIFETIME']
        refresh_expiration = timezone_now() + settings.SIMPLE_JWT['REFRESH_TOKEN_LIFETIME']

        # Format datetime according to REST_FRAMEWORK settings
        datetime_format = settings.REST_FRAMEWORK.get('DATETIME_FORMAT', '%Y-%m-%d %H:%M:%S')
        access_expiration_str = access_expiration.strftime(datetime_format)
        refresh_expiration_str = refresh_expiration.strftime(datetime_format)

        # Serialize user data
        user_serializer = UserSerializer(user, context={'request': request})

        response_data = {
            'access': access_token_str,
            'refresh': refresh_token_str,
            'user': user_serializer.data,
            'access_expiration': access_expiration_str,
            'refresh_expiration': refresh_expiration_str,
        }

        return Response(response_data, status=status.HTTP_200_OK)


class ResendEmailConfirmationView(APIView):
    permission_classes = (AllowAny,)

    def post(self, request: Request):
        token = request.data.get('token')
        if not token:
            return Response({'Status': False, 'code': 'Token not found'}, status=status.HTTP_400_BAD_REQUEST)

        user_id = cache.get(f'{RESEND_VERIFICATION_TOKEN_CACHE_KEY}{token}')
        if not user_id:
            return Response({'Status': False, 'code': 'Token not found'}, status=status.HTTP_400_BAD_REQUEST)

        # check if verification email in progress
        verification_in_progress = cache.get(f'{RESEND_VERIFICATION_TOKEN_CACHE_KEY}{user_id}')
        if verification_in_progress:
            return Response({'Status': False, 'code': 'Email confirmation in progress'}, status=status.HTTP_400_BAD_REQUEST)

        lang = request.data.get('lang', 'en')
        if lang not in dict(settings.LANGUAGES):
            return Response(status=status.HTTP_400_BAD_REQUEST, data={
                'result': f'Lang {lang} not found'})

        # Activate the language for this request
        translation_activate(lang)
        setattr(request, 'LANGUAGE_CODE', translation_get_language())

        user = User.objects.get(id=user_id)
        email_address: EmailAddress = EmailAddress.objects.get(
            user=user,
            email=user.email,
        )
        if email_address.verified:
            return Response({'Status': False, 'code': 'Email already verified'}, status=status.HTTP_400_BAD_REQUEST)
        logger.info(f"Sending email confirmation to {user.email}")
        email_address.send_confirmation(request)

        # set verification in progress by user id
        cache.set(f'{RESEND_VERIFICATION_TOKEN_CACHE_KEY}{user_id}', 1, timeout=300)  # 5 min for next attempt
        return Response({'Status': True}, status=status.HTTP_200_OK)

class PasswordResetConfirmView(TemplateView):
    template_name = 'accounts/password_reset_confirm.html'

    def get(self, request, *args, **kwargs):
        # Make the token and uid available to the template
        context = self.get_context_data(**kwargs)
        context['token'] = kwargs.get('token')
        context['uid'] = kwargs.get('uidb64')
        return self.render_to_response(context)
