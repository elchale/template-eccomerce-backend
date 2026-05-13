import re
import requests

from django.conf import settings
from django.core.cache import cache
from rest_framework.exceptions import ValidationError

from users.exceptions import MaxCaptchaSkipAttempts

class CaptchaProcessor:
    CAPTCHA_ENABLED = settings.CAPTCHA_ENABLED
    PASSED_PREFIX = 'passed:'
    MAX_ERROR_ATTEMPTS = 6
    CACHE_TIMEOUT = settings.CAPTCHA_TIMEOUT

    def __init__(self, uid, ip, captcha_response, skip_extra_checks=False):
        self.uid = uid
        self.ip = ip
        self.captcha_response = captcha_response
        self.skip_extra_checks = skip_extra_checks

    def get_ckey(self):
        return f'{self.uid}{self.ip}'

    @classmethod
    def cache_key(cls, value):
        return f'{cls.PASSED_PREFIX}{value}'

    @classmethod
    def get_cache(cls, key):
        ckey = cls.cache_key(key)
        data = cache.get(ckey)
        return data

    @classmethod
    def get_cache_ttl(cls, key):
        ckey = cls.cache_key(key)
        return cache.ttl(ckey)

    @classmethod
    def del_cache(cls, key):
        ckey = cls.cache_key(key)
        cache.delete(ckey)

    @classmethod
    def set_cache(cls, key, timeout=None, data=None):
        ckey = cls.cache_key(key)
        if data is None:
            data = cls.MAX_ERROR_ATTEMPTS
        cache.set(ckey, data, timeout or cls.CACHE_TIMEOUT)

    def is_captcha_required(self):
        if self.ip in ['127.0.0.1', 'localhost'] or (self.ip and re.match(settings.CAPTCHA_ALLOWED_IP_MASK, self.ip)):
            return False

        if self.is_captcha_passed():
            return False
        return True

    def check(self):
        if not self.CAPTCHA_ENABLED:
            return

        if not self.skip_extra_checks:
            if not self.is_captcha_required():
                return

        if not self.captcha_response or self.captcha_response == '':
            raise ValidationError({
                'message': 'invalidate data',
                'type': 'captcha_required'
            })
        try:
            self._captcha_check(self.captcha_response)
        except Exception:
            self.del_captcha_pass()
            raise


    @classmethod
    def _captcha_check(cls, response, secret=settings.RECAPTCHA_SECRET):
        r = requests.post(
            'https://www.google.com/recaptcha/api/siteverify',
            data={'secret': secret, 'response': response},
            timeout=10,
        )
        if not r.json()['success']:
            raise ValidationError({
                'message': 'bad captcha!',
                'type': 'bad_captcha'
            })

    def decrease_attempts(self, custom_exception=None):
        data = self.get_cache(self.get_ckey())
        if data is not None:
            ttl = self.get_cache_ttl(self.get_ckey())
            data -= 1
            if data <= 0:
                self.del_captcha_pass()
                if custom_exception:
                    raise custom_exception()
                raise MaxCaptchaSkipAttempts()
            else:
                self.set_cache(self.get_ckey(), data=data, timeout=ttl)

    def del_captcha_pass(self):
        self.del_cache(self.get_ckey())

    def set_captcha_passed(self):
        if not self.is_captcha_passed():
            self.set_cache(self.get_ckey(), timeout=180)

    def is_captcha_passed(self):
        return bool(self.get_cache(self.get_ckey()))

