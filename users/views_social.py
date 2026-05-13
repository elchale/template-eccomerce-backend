import logging
from ipware import get_client_ip
from django_user_agents.utils import get_user_agent

from dj_rest_auth.registration.views import SocialLoginView
from allauth.socialaccount.providers.google.views import GoogleOAuth2Adapter
from allauth.socialaccount.providers.oauth2.client import OAuth2Client

from users.serializers.social import GoogleLoginSerializer
from users.models import LoginHistory

logger = logging.getLogger(__name__)


class CompatOAuth2Client(OAuth2Client):
    """
    Compatibility wrapper for dj-rest-auth 7.x + django-allauth 65.x.

    dj-rest-auth passes `scope` as a positional arg but allauth removed it
    from OAuth2Client.__init__, causing 'multiple values for scope_delimiter'.
    This wrapper absorbs the extra `scope` argument.
    """

    def __init__(self, request, consumer_key, consumer_secret,
                 access_token_method, access_token_url, callback_url,
                 scope=None, **kwargs):
        super().__init__(
            request, consumer_key, consumer_secret,
            access_token_method, access_token_url, callback_url,
            **kwargs,
        )
        self.scope = scope


class GoogleLoginView(SocialLoginView):
    """
    POST /auth/google/

    Accepts either:
    - `code`         — authorisation code from Google's popup/redirect flow
    - `access_token` — already-exchanged access token (less common)
    - `id_token`     — Google ID token (for one-tap / credential flows)

    On success returns the same JWT response shape as the standard login
    endpoint: { access, refresh, user, access_expiration, refresh_expiration }.
    """

    adapter_class = GoogleOAuth2Adapter
    callback_url = 'postmessage'
    client_class = CompatOAuth2Client
    serializer_class = GoogleLoginSerializer

    def get_response(self):
        """
        After a successful social login, record a LoginHistory entry so the
        IP-tracking audit trail stays consistent with password-based logins.
        """
        response = super().get_response()

        try:
            user = self.user  # set by SocialLoginView after login completes
            if user and user.pk:
                request = self.request
                ip = get_client_ip(request)[0]
                user_agent_obj = get_user_agent(request)
                LoginHistory.objects.create(
                    user=user,
                    ip=ip,
                    user_agent=user_agent_obj.ua_string[:255],
                )
                logger.info(
                    f"[Google OAuth] Login recorded for user id={user.pk}, ip={ip}."
                )
        except Exception as exc:
            # Never let audit-trail code break the login response.
            logger.warning(f"[Google OAuth] Could not record login history: {exc}")

        return response
