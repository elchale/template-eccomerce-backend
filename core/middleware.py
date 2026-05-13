"""Core middleware.

Provides:
- RequestIdMiddleware  — reads/generates X-Request-Id, echoes in response
- AccessLogsMiddleware — structured per-request log (method/path/status/ms/user)
- ResponseTimeMiddleware — X-Response-Time-Ms response header
"""
import logging
import threading
import time
import uuid

from django.utils import translation

logger = logging.getLogger(__name__)
access_logger = logging.getLogger('access')

# Thread-local storage for request_id so log filters can pick it up
_local = threading.local()


def get_current_request_id() -> str:
    return getattr(_local, 'request_id', '')


class RequestIdMiddleware:
    """Read or generate X-Request-Id header; echo it back in the response."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request_id = request.META.get('HTTP_X_REQUEST_ID') or str(uuid.uuid4())
        request.request_id = request_id
        _local.request_id = request_id

        response = self.get_response(request)
        response['X-Request-Id'] = request_id
        return response


class AccessLogsMiddleware:
    """Log one line per request: method, path, status, duration, user, ip."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        start = time.monotonic()
        response = self.get_response(request)
        duration_ms = round((time.monotonic() - start) * 1000, 1)

        user_id = None
        if hasattr(request, 'user') and request.user.is_authenticated:
            user_id = request.user.pk

        ip = (
            request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip()
            or request.META.get('REMOTE_ADDR', '')
        )

        access_logger.info(
            'request',
            extra={
                'method': request.method,
                'path': request.path,
                'status': response.status_code,
                'duration_ms': duration_ms,
                'user_id': user_id,
                'ip': ip,
                'request_id': getattr(request, 'request_id', ''),
            },
        )
        return response


class ResponseTimeMiddleware:
    """Attach X-Response-Time-Ms header to every response."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        start = time.monotonic()
        response = self.get_response(request)
        duration_ms = round((time.monotonic() - start) * 1000, 1)
        response['X-Response-Time-Ms'] = str(duration_ms)
        return response


# Language middleware stubs (backward compat)
class force_default_language_middleware:
    """Middleware that forces the language selected in the settings."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        translation.activate(translation.get_language())
        response = self.get_response(request)
        return response


class SetupTranslationsLang:
    """Middleware that sets up language based on user preferences."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        return response
