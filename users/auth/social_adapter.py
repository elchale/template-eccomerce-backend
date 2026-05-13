import logging
from ipware import get_client_ip
from django_user_agents.utils import get_user_agent

from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.account.models import EmailAddress

from users.models import Profile, LoginHistory

logger = logging.getLogger(__name__)


class CustomSocialAccountAdapter(DefaultSocialAccountAdapter):
    """
    Custom social account adapter that enforces the following security rules:

    1. If a Google login comes in and an UNVERIFIED account already exists with
       the same email, the Google account takes over:
       - The social account is linked to the existing user.
       - The email is marked as verified.
       - The password is set to unusable (preventing password-based login).
       This prevents an attacker from squatting on a victim's email with an
       unverified account.

    2. If the email already belongs to a verified account (no social link yet),
       allauth's default connect-on-existing-email logic handles the linking.

    3. Brand-new Google signups get:
       - Email auto-verified (Google already verified it).
       - Unusable password.
       - Profile created (also handled by the post_save signal, but we ensure it
         here as a safety net).
    """

    def pre_social_login(self, request, sociallogin):
        """
        Called after a user has successfully authenticated via Google but before
        the login / account-creation flow completes.

        Security: if an UNVERIFIED local account exists with the same email,
        take it over — link the social account and verify the email.
        """
        if sociallogin.is_existing:
            # Already linked — nothing special to do.
            return

        email = self._get_email(sociallogin)
        if not email:
            return

        try:
            existing_email_address = EmailAddress.objects.select_related('user').get(
                email__iexact=email
            )
        except EmailAddress.DoesNotExist:
            # Brand-new user — handled in save_user().
            return

        existing_user = existing_email_address.user

        if not existing_email_address.verified:
            # SECURITY: Unverified account takeover.
            # Google has already verified ownership of this email, so we trust it.
            logger.info(
                f"[Google OAuth] Taking over unverified account for email '{email}' "
                f"(user id={existing_user.pk})."
            )
            existing_email_address.verified = True
            existing_email_address.primary = True
            existing_email_address.save()

            existing_user.set_unusable_password()
            existing_user.save(update_fields=['password'])

            # Ensure Profile exists (signal should have created it, but be safe).
            Profile.objects.get_or_create(user=existing_user)

        # Connect this Google social account to the existing user so the login
        # proceeds without creating a duplicate user record.
        sociallogin.connect(request, existing_user)

    def save_user(self, request, sociallogin, form=None):
        """
        Called when a brand-new user is created via social login.
        Sets an unusable password — the user authenticates only via Google.
        """
        user = super().save_user(request, sociallogin, form=form)

        # Make sure the password is unusable for new social-only accounts.
        if user.has_usable_password():
            user.set_unusable_password()
            user.save(update_fields=['password'])

        # Ensure Profile exists (the post_save signal normally handles this).
        Profile.objects.get_or_create(user=user)

        # Record login history if we have a request.
        self._record_login_history(request, user)

        logger.info(
            f"[Google OAuth] New user created via Google: email='{user.email}', "
            f"id={user.pk}."
        )
        return user

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get_email(self, sociallogin) -> str:
        """Extract email from sociallogin extra data, falling back to account."""
        email = sociallogin.account.extra_data.get('email', '')
        if not email and sociallogin.email_addresses:
            email = sociallogin.email_addresses[0].email
        return (email or '').lower().strip()

    def _record_login_history(self, request, user) -> None:
        """Record a LoginHistory entry for audit purposes."""
        if request is None:
            return
        try:
            ip = get_client_ip(request)[0]
            user_agent_obj = get_user_agent(request)
            LoginHistory.objects.create(
                user=user,
                ip=ip,
                user_agent=user_agent_obj.ua_string[:255],
            )
        except Exception as exc:
            logger.warning(f"[Google OAuth] Could not record login history: {exc}")
