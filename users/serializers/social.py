from dj_rest_auth.registration.serializers import SocialLoginSerializer


class GoogleLoginSerializer(SocialLoginSerializer):
    """
    Serializer for Google OAuth login.

    The frontend sends the authorisation code obtained from Google Identity
    Services (the popup / redirect flow). dj-rest-auth + allauth validate the
    code against Google and exchange it for user information.

    No extra fields are required — the base SocialLoginSerializer already
    handles `code`, `access_token`, and `id_token`.
    """
    pass
