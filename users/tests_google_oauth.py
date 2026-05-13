"""
Tests for Google OAuth integration.

Covers:
- CustomSocialAccountAdapter.pre_social_login:
    - Unverified account takeover (email verified, password set unusable, social linked)
    - Verified account linking (social linked to existing verified user)
    - Brand-new user path (no existing account)
- CustomSocialAccountAdapter.save_user:
    - Password set to unusable
    - Profile created
- AccountAdapter.validate_unique_email:
    - Raises google_account_exists error when email belongs to a social account
- GoogleLoginView URL registration
- setup_google_oauth management command
"""
import pytest
from unittest.mock import MagicMock, patch
from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from allauth.account.models import EmailAddress
from allauth.socialaccount.models import SocialAccount, SocialLogin, SocialApp
from django.contrib.sites.models import Site
from rest_framework.exceptions import ValidationError

from users.auth.social_adapter import CustomSocialAccountAdapter
from users.auth.adapters import AccountAdapter
from users.models import Profile

User = get_user_model()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_request():
    factory = RequestFactory()
    request = factory.post('/auth/google/')
    request.META['HTTP_USER_AGENT'] = 'TestBrowser/1.0'
    return request


def _make_social_login(email: str, is_existing: bool = False, user=None):
    """Build a minimal mock SocialLogin for unit tests."""
    sl = MagicMock(spec=SocialLogin)
    sl.is_existing = is_existing
    sl.account = MagicMock()
    sl.account.extra_data = {'email': email}
    sl.email_addresses = []
    if user:
        sl.user = user
    return sl


# ---------------------------------------------------------------------------
# CustomSocialAccountAdapter tests
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestCustomSocialAccountAdapterPreSocialLogin(TestCase):

    def setUp(self):
        self.adapter = CustomSocialAccountAdapter()
        self.request = _make_request()

    def test_unverified_account_takeover(self):
        """
        When a Google login arrives for an email that already has an UNVERIFIED
        allauth EmailAddress:
        - The EmailAddress is marked verified.
        - The user's password is set to unusable.
        - sociallogin.connect() is called to link the accounts.
        """
        user = User.objects.create_user(
            username='testuser1',
            email='takeover@example.com',
            password='ValidPass123!',
        )
        email_address = EmailAddress.objects.create(
            user=user,
            email='takeover@example.com',
            verified=False,
            primary=True,
        )

        sl = _make_social_login('takeover@example.com')

        self.adapter.pre_social_login(self.request, sl)

        email_address.refresh_from_db()
        user.refresh_from_db()

        assert email_address.verified is True, "Email should be verified after takeover"
        assert not user.has_usable_password(), "Password should be unusable after takeover"
        sl.connect.assert_called_once_with(self.request, user)

    def test_verified_account_linking(self):
        """
        When a Google login arrives for an email that already has a VERIFIED
        allauth EmailAddress, the social account is linked to that user.
        """
        user = User.objects.create_user(
            username='testuser2',
            email='verified@example.com',
            password='ValidPass123!',
        )
        EmailAddress.objects.create(
            user=user,
            email='verified@example.com',
            verified=True,
            primary=True,
        )

        sl = _make_social_login('verified@example.com')

        self.adapter.pre_social_login(self.request, sl)

        # connect() is called regardless so allauth proceeds with the existing user.
        sl.connect.assert_called_once_with(self.request, user)
        # Password should NOT be touched for an already-verified user.
        user.refresh_from_db()
        assert user.has_usable_password(), "Password should remain usable for verified existing users"

    def test_brand_new_email_skips_connect(self):
        """
        When no EmailAddress record exists for the incoming email,
        pre_social_login should do nothing (new user flow handled by save_user).
        """
        sl = _make_social_login('newuser@example.com')

        # Should not raise and should not call connect().
        self.adapter.pre_social_login(self.request, sl)

        sl.connect.assert_not_called()

    def test_already_linked_sociallogin_is_skipped(self):
        """
        If the social login is_existing=True (already linked), pre_social_login
        returns early without touching anything.
        """
        sl = _make_social_login('linked@example.com', is_existing=True)

        self.adapter.pre_social_login(self.request, sl)

        sl.connect.assert_not_called()

    def test_profile_created_during_takeover(self):
        """
        During an unverified account takeover a Profile is ensured.
        """
        user = User.objects.create_user(
            username='testuser3',
            email='profiletest@example.com',
            password='pass',
        )
        # Manually delete profile to simulate missing profile
        Profile.objects.filter(user=user).delete()

        EmailAddress.objects.create(
            user=user,
            email='profiletest@example.com',
            verified=False,
            primary=True,
        )

        sl = _make_social_login('profiletest@example.com')
        self.adapter.pre_social_login(self.request, sl)

        assert Profile.objects.filter(user=user).exists(), "Profile should be created during takeover"


@pytest.mark.django_db
class TestCustomSocialAccountAdapterSaveUser(TestCase):

    def setUp(self):
        self.adapter = CustomSocialAccountAdapter()
        self.request = _make_request()

    def test_save_user_sets_unusable_password(self):
        """New social users should have an unusable password after save_user."""
        user = User.objects.create_user(
            username='socialuser',
            email='social@example.com',
            password='SomePass!',
        )
        sl = _make_social_login('social@example.com', user=user)

        # Patch the parent class save_user so we avoid the full allauth pipeline.
        with patch(
            'users.auth.social_adapter.DefaultSocialAccountAdapter.save_user',
            return_value=user,
        ):
            saved_user = self.adapter.save_user(self.request, sl)

        saved_user.refresh_from_db()
        assert not saved_user.has_usable_password()

    def test_save_user_creates_profile(self):
        """Profile should exist after save_user."""
        user = User.objects.create_user(
            username='socialuser2',
            email='social2@example.com',
            password='SomePass!',
        )
        Profile.objects.filter(user=user).delete()

        sl = _make_social_login('social2@example.com', user=user)

        with patch(
            'users.auth.social_adapter.DefaultSocialAccountAdapter.save_user',
            return_value=user,
        ):
            self.adapter.save_user(self.request, sl)

        assert Profile.objects.filter(user=user).exists()


# ---------------------------------------------------------------------------
# AccountAdapter.validate_unique_email tests
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestAccountAdapterValidateUniqueEmail(TestCase):

    def setUp(self):
        self.request = _make_request()
        self.adapter = AccountAdapter(self.request)

    def test_google_account_error_when_social_linked(self):
        """
        If the email belongs to a user with an existing SocialAccount, raise
        a ValidationError with type='google_account_exists'.
        """
        user = User.objects.create_user(
            username='googleonly',
            email='googleonly@example.com',
        )
        user.set_unusable_password()
        user.save()
        EmailAddress.objects.create(
            user=user,
            email='googleonly@example.com',
            verified=True,
            primary=True,
        )

        # Create a minimal SocialApp first (required by allauth FK).
        site, _ = Site.objects.get_or_create(pk=1, defaults={'domain': 'example.com', 'name': 'example.com'})
        app, _ = SocialApp.objects.get_or_create(
            provider='google',
            defaults={'name': 'Google', 'client_id': 'test-id', 'secret': 'test-secret'},
        )
        app.sites.add(site)

        SocialAccount.objects.create(
            user=user,
            provider='google',
            uid='google-uid-123',
            extra_data={},
        )

        with pytest.raises(ValidationError) as exc_info:
            self.adapter.validate_unique_email('googleonly@example.com')

        detail = exc_info.value.detail
        assert detail.get('type') == 'google_account_exists'

    def test_regular_duplicate_email_raises_wrong_data(self):
        """
        If the email exists but is NOT linked to a social account, the original
        'wrong_data' error is raised.
        """
        user = User.objects.create_user(
            username='pwduser',
            email='pwduser@example.com',
            password='pass123!',
        )
        EmailAddress.objects.create(
            user=user,
            email='pwduser@example.com',
            verified=True,
            primary=True,
        )

        with pytest.raises(ValidationError) as exc_info:
            self.adapter.validate_unique_email('pwduser@example.com')

        detail = exc_info.value.detail
        assert detail.get('type') == 'wrong_data'

    def test_new_email_passes_validation(self):
        """An email that doesn't exist yet should pass without raising."""
        result = self.adapter.validate_unique_email('brand_new@example.com')
        assert result == 'brand_new@example.com'


# ---------------------------------------------------------------------------
# URL registration test
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestGoogleLoginUrl(TestCase):

    def test_google_login_url_resolves(self):
        from django.urls import reverse, resolve
        url = reverse('google_login')
        assert url == '/auth/google/'
        resolved = resolve('/auth/google/')
        assert resolved.view_name == 'google_login'


# ---------------------------------------------------------------------------
# Management command test
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestSetupGoogleOauthCommand(TestCase):

    def setUp(self):
        # Ensure Site pk=1 exists (SITE_ID=1 is configured in settings).
        Site.objects.get_or_create(pk=1, defaults={'domain': 'example.com', 'name': 'example.com'})

    def test_creates_social_app(self):
        from django.core.management import call_command
        from io import StringIO

        # Remove any existing app to start clean.
        SocialApp.objects.filter(provider='google').delete()

        out = StringIO()
        call_command('setup_google_oauth', stdout=out)

        assert SocialApp.objects.filter(provider='google').exists()
        assert 'Created Google SocialApp' in out.getvalue()

    def test_idempotent_update(self):
        """Running the command twice should update, not create a second record."""
        from django.core.management import call_command
        from io import StringIO

        # First run.
        call_command('setup_google_oauth', stdout=StringIO())
        count_after_first = SocialApp.objects.filter(provider='google').count()

        # Second run.
        out = StringIO()
        call_command('setup_google_oauth', stdout=out)
        count_after_second = SocialApp.objects.filter(provider='google').count()

        assert count_after_first == count_after_second == 1
        assert 'Updated Google SocialApp' in out.getvalue()
