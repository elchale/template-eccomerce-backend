import logging
from typing import cast
from ipware import get_client_ip
from celery import Task

from django.conf import settings
from user_agents.parsers import UserAgent
from django_user_agents.utils import get_user_agent
from django.db.models import Model
from django.db.transaction import atomic
from django.core.cache import cache
from django.contrib.auth import get_user_model
from django.contrib.sites.models import Site
from django.contrib.sites.shortcuts import get_current_site
from rest_framework import serializers
from rest_framework.exceptions import ValidationError, MethodNotAllowed
from django.utils.translation import gettext_lazy as _
from dj_rest_auth.registration.serializers import RegisterSerializer as BaseRegisterSerializer
from dj_rest_auth.serializers import LoginSerializer as BaseLoginSerializer
from dj_rest_auth.serializers import PasswordChangeSerializer as BasePasswordChangeSerializer
from dj_rest_auth.serializers import PasswordResetConfirmSerializer as BasePasswordResetConfirmSerializer
from dj_rest_auth.serializers import PasswordResetSerializer as BasePasswordResetSerializer
from dj_rest_auth.serializers import UserDetailsSerializer

from users.models import Profile, LoginHistory
from users.captcha import CaptchaProcessor
from users.utils import RegisterUserCheck, generate_cool_username
from users.exceptions import AccountNotActive, TwoFAFailed, Wrong2FATooManyTimes
from users.cache_keys import (
    RESEND_VERIFICATION_TOKEN_CACHE_KEY,
    RESEND_VERIFICATION_TOKEN_REVERSED_CACHE_KEY,
)
from users.tasks import (
    notify_user_duplicate_registration,
    notify_user_ip_changed,
    notify_failed_login,
    send_password_change_notification,
)

from utils.generic_functions import generate_random_string

logger = logging.getLogger(__name__)

User: Model = get_user_model()

class UserSerializer(UserDetailsSerializer):
    """
    This is used by dj-rest-auth tp serialize the user data in the login and register response

    It must be used only in settings.REST_AUTH.USER_DETAILS_SERIALIZER
    """
    actions_freezed_till = serializers.DateTimeField(source='profile.actions_freezed_till', read_only=True)

    class Meta(UserDetailsSerializer.Meta):
        fields = ('username', 'email', 'first_name', 'last_name', 'is_staff', 'actions_freezed_till')
        extra_kwargs = {'pk': {'read_only': False, 'required': False}}

    def create(self, *args, **kwargs):
        raise MethodNotAllowed('create')


class GCodeMixIn(serializers.Serializer):
    """
    This is a helper to check 2FA

    Currently it does nothing, but it can be used to check 2FA in the future
    """
    googlecode = serializers.CharField(required=False, allow_blank=True)

    def check_2fa_for_user(self, username, gcode):
        return
        # TODO implement
        # if not TwoFactorSecretTokens.check_g_code(username, gcode):
        #     raise TwoFAFailed()


class LoginSerializer(GCodeMixIn, BaseLoginSerializer):
    """
    This is used by dj-rest-auth to authenticate users

    It must be used only in settings.REST_AUTH.LOGIN_SERIALIZER
    """
    captcha = serializers.CharField(required=False, allow_blank=True)
    email = serializers.EmailField(required=True)

    def validate(self, attrs):
        request = self._context['request']
        ip = get_client_ip(request)[0]
        email = attrs.get('email').lower()
        password = attrs.get('password')

        captcher = CaptchaProcessor(
            email,
            ip,
            attrs.get('captcha'),
        )
        captcher.check()

        user_agent: UserAgent = get_user_agent(request)
        device = user_agent.device.family
        os = f'({user_agent.os.family} {user_agent.os.version_string})'
        browser = f'({user_agent.browser.family} {user_agent.browser.version_string})'

        fields = {
            'user': email,
            'ip': ip,
            'browser': browser,
            'os': os,
            'device': device,
        }

        try:
            user_object = User.objects.filter(email=email).first()

            # User not found
            if not user_object:
                raise ValidationError({'message': _('Unable to log in with provided credentials.'), 'type': 'wrong_data'})

            # User password was removed
            if not user_object.password:
                raise ValidationError({'message': _('Please reset your password'), 'type': 'reset_psw'})

            if not user_object.is_active:
                raise AccountNotActive({'message': _('User account is disabled.'), 'type': 'account_block'})

            # Call the BaseLoginSerializer validate method
            user = self._validate_email(email, password)

            if not user:
                raise ValidationError({'message': _('Unable to log in with provided credentials.'), 'type': 'wrong_data'})

            try:
                # Call the BaseLoginSerializer validate_email_verification_status method
                # NOTE this can be skipped if settings.EMAIL_VERIFICATION = False
                self.validate_email_verification_status(user)

            except ValidationError:
                # NOTE this token is for re-requesting a verification email
                current_token = cache.get(f'{RESEND_VERIFICATION_TOKEN_REVERSED_CACHE_KEY}{user.id}')
                if not current_token:
                    current_token = generate_random_string(32)
                    cache.set(f'{RESEND_VERIFICATION_TOKEN_REVERSED_CACHE_KEY}{user.id}', current_token, timeout=1800) # 30 minutes
                    cache.set(f'{RESEND_VERIFICATION_TOKEN_CACHE_KEY}{current_token}', user.id, timeout=1800)
                raise AccountNotActive({
                    'error': 'email_not_verified',
                    'type': 'email_not_verified',
                    'token': current_token
                })

            self.validate_kyc(user)

            attrs['user'] = user
            captcher.set_captcha_passed()

        except AccountNotActive:
            # NOTE we are not sending mail
            captcher.del_captcha_pass()
            raise

        except Exception as exc_ch:
            captcher.del_captcha_pass()
            profile = Profile.objects.filter(user__email=email).first()
            if profile:
                cast(Task, notify_failed_login).apply_async((profile.user_id,))
            raise exc_ch

        try:
            self.check_2fa_for_user(attrs['user'], attrs.get('googlecode', None))
        except TwoFAFailed:
            captcher.decrease_attempts(Wrong2FATooManyTimes)
            raise

        captcher.del_captcha_pass()

        # Send email if IP changed
        ip_history = list(LoginHistory.objects.filter(user=user).values_list('ip', flat=True))
        if ip_history and ip not in ip_history:
            device_type = "Mobil" if user_agent.is_mobile else \
                "Tableta" if user_agent.is_tablet else \
                "PC" if user_agent.is_pc else \
                "Bot" if user_agent.is_bot else "Desconocido"

            cast(Task, notify_user_ip_changed).apply_async((user.id, ip, device_type, os, browser))

        LoginHistory(
            user=user,
            ip=ip,
            user_agent=user_agent.ua_string[:255]
        ).save()

        # Update register ip if necessary
        # if not user_object.profile.register_ip:
        #     profile: Profile = user.profile
        #     profile.register_ip = ip
        #     profile.save()

        logger.info(f'[User auth success] user: {attrs["user"]},  ip: {ip}, browser: {fields["browser"]}, os: {fields["os"]}, device: {fields["device"]}')
        return attrs

    def validate_kyc(self, user: User) -> None:
        # TODO implement
        return

        # if not IS_KYC_REQUIRED:
        #     return
        # if not UserKYC.valid_for_user(user):
        #     raise ValidationError({'message': _('Unable to log in due to KYC restrictions.'), 'type': 'wrong_data'})

class RegisterSerializer(BaseRegisterSerializer):
    """
    This is used by dj-rest-auth to register users

    It must be used only in settings.REST_AUTH.REGISTER_SERIALIZER
    """
    email = serializers.EmailField(required=True)
    username = serializers.CharField(required=False)

    captchaResponse = serializers.CharField(required=settings.CAPTCHA_ENABLED, allow_blank=True)
    first_name = serializers.CharField(required=False)
    last_name = serializers.CharField(required=False)

    def validate_username(self, username):
        if not RegisterUserCheck.validate_score_email(username):
            raise ValidationError({
                'message': _('similar username was recently used'),
                'type': 'registration_similar_username'
            })
        return username

    def validate_email(self, username):
        user_exist = User.objects.filter(email=username).first()
        if user_exist:
            request = self._context['request']
            ip = get_client_ip(request)[0]
            user_agent: UserAgent = get_user_agent(request)
            os = f'({user_agent.os.family} {user_agent.os.version_string})'
            browser = f'({user_agent.browser.family} {user_agent.browser.version_string})'

            cast(Task, notify_user_duplicate_registration).apply_async((username, ip, browser, os))

            raise ValidationError({'message': _('Account creation failed. Please try again later.'), 'type': 'registration_failed'})
        return username

    def validate(self, data):
        if settings.DISABLE_REGISTRATION:
            raise ValidationError({
                'message': 'Registration is disabled',
                'type': 'registration_disable'
            })

        # Check if Site configuration exists
        self._context['request']
        email = data.get('email').lower()
        captcher = CaptchaProcessor(
            email,
            None,
            data.get('captchaResponse'),
            skip_extra_checks=True,
        )
        captcher.check()

        data['email'] = email
        data = super(RegisterSerializer, self).validate(data)
        return data

    def get_cleaned_data(self):
        return {
            'first_name': self.validated_data.get('first_name', ''),
            'last_name': self.validated_data.get('last_name', ''),
            'username': self.validated_data.get('username', ''),
            'password1': self.validated_data.get('password1', ''),
            'email': self.validated_data.get('email', '')
        }

    def save(self, request):
        request._request.lang = self.validated_data.get('lang', 'en')
        self.validated_data['username'] = generate_cool_username()

        with atomic():
            # Double-check site configuration before saving
            try:
                site = get_current_site(request._request)
                if not site:
                    raise Site.DoesNotExist()
            except Site.DoesNotExist:
                logger.error("Site.DoesNotExist error when creating user")
                raise ValidationError({
                    'message': _('Registration is currently unavailable. Please try again later.'),
                    'type': 'site_config_missing'
                })

            user = super().save(request)
            profile: Profile = user.profile
            # profile.register_ip = next(iter(get_client_ip(request) or []), None)
            profile.save()
            logger.info(f"User created with email {user.email} and username '{user.username}'")

        RegisterUserCheck.update_last_emails()
        # Return user but no tokens will be generated for inactive users
        return user


class PasswdChangeSerializer(GCodeMixIn, BasePasswordChangeSerializer):

    def validate_old_password(self, value):
        try:
            value = super(PasswdChangeSerializer, self).validate_old_password(value)
        except ValidationError:
            raise ValidationError({'msg': 'Invalid password', 'type': 'invalid_password'})

        return value

    def save(self):
        ret = BasePasswordChangeSerializer.save(self)
        profile: Profile = self.user.profile
        profile.set_actions_freeze(settings.ACTIONS_FREEZE_ON_PWD_CHANGE)
        send_password_change_notification.delay(self.user.pk)
        return ret


class PasswordResetSerializer(GCodeMixIn, BasePasswordResetSerializer):
    captcha = serializers.CharField(required=False, allow_blank=True)

    def get_email_options(self):
        # NOTE this assumes that when DEBUG is true we are testing in http
        return {
            'password_reset_url': f"{'http' if settings.DEBUG else 'https'}://{settings.DOMAIN}/reset-password/g/{{key}}/",
        }

    def validate(self, attrs):
        attrs = BasePasswordResetSerializer.validate(self, attrs)
        captcher = CaptchaProcessor(
            attrs.get('email').lower(),
            None,
            attrs.get('captcha'),
            skip_extra_checks=True,
        )
        captcher.check()
        return attrs


class PasswordResetConfirmSerializer(BasePasswordResetConfirmSerializer):
    def save(self):
        ret = BasePasswordResetConfirmSerializer.save(self)
        profile: Profile = self.user.profile
        profile.set_actions_freeze(settings.ACTIONS_FREEZE_ON_PWD_RESET)
        return ret
