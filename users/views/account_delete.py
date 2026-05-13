"""GDPR soft-delete (account anonymisation) endpoint."""
import logging

from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

logger = logging.getLogger(__name__)

User = get_user_model()


class UserAccountDeleteView(APIView):
    """DELETE /api/users/me/

    Soft-delete: anonymises PII, sets is_active=False, blacklists every
    outstanding refresh token so the httpOnly cookie can't mint new
    access tokens after the call returns. Order/OrderItem rows are
    preserved for accounting.

    Requires ``X-Confirm-Password`` header — re-authenticates the live
    user before the destructive write so a stolen access token alone
    can't trigger the flow. Scoped throttle (``account_delete`` =
    5/minute) caps password-guessing attempts on the confirm field.
    """

    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'account_delete'

    def delete(self, request):
        confirm_password = request.META.get('HTTP_X_CONFIRM_PASSWORD', '')
        if not confirm_password:
            return Response(
                {'message': 'Se requiere X-Confirm-Password para eliminar la cuenta.', 'type': 'confirmation_required', 'field_errors': {}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = request.user
        if not user.check_password(confirm_password):
            return Response(
                {'message': 'Contraseña incorrecta.', 'type': 'invalid_password', 'field_errors': {}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            user_id = user.pk
            anon_email = f'deleted-{user_id}@anonymized.local'

            # Anonymise the User row
            user.email = anon_email
            user.username = f'deleted_{user_id}'
            user.first_name = 'Deleted'
            user.last_name = 'User'
            user.is_active = False
            user.set_unusable_password()
            user.save()

            # Blank LoginHistory PII
            from users.models import LoginHistory
            LoginHistory.objects.filter(user=user).update(ip=None, user_agent='')

            # Delete addresses
            from users.models import UserAddress
            UserAddress.objects.filter(user=user).delete()

            # Blacklist every outstanding refresh token so the httpOnly
            # cookie can't be used to mint access tokens for this user
            # after the soft-delete returns. Narrow the import-error swallow
            # to ImportError only — other failures must propagate so the
            # transaction rolls back rather than silently leaving valid
            # refresh tokens behind.
            try:
                from rest_framework_simplejwt.token_blacklist.models import (
                    BlacklistedToken,
                    OutstandingToken,
                )
            except ImportError:
                logger.warning(
                    'simplejwt token_blacklist not installed — refresh tokens '
                    'for user_id=%s NOT blacklisted on soft-delete',
                    user_id,
                )
            else:
                for outstanding in OutstandingToken.objects.filter(user=user):
                    BlacklistedToken.objects.get_or_create(token=outstanding)

            logger.info('Account soft-deleted for user_id=%s', user_id)

        return Response(status=status.HTTP_204_NO_CONTENT)
