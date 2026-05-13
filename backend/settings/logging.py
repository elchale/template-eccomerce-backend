"""Logging configuration.

Supports two output formats controlled by LOG_FORMAT env var:
  - text  (default in DEBUG)   — plain human-readable StreamHandler output
  - json  (default in prod)    — structured JSON via python-json-logger

When django-log-request-id is installed, every log record gets a
request_id field attached by RequestIDFilter.
"""
import os

from .env import env
from .common import DEBUG

LOG_FORMAT = env('LOG_FORMAT', default='text' if DEBUG else 'json')

_use_json = LOG_FORMAT == 'json'

# Try to detect optional libraries
try:
    from pythonjsonlogger import jsonlogger  # noqa: F401
    _json_logger_available = True
except ImportError:
    _json_logger_available = False

try:
    from log_request_id.filters import RequestIDFilter  # noqa: F401
    _request_id_filter_available = True
except ImportError:
    _request_id_filter_available = False


_filters = {}
_handler_filters = []

if _request_id_filter_available:
    _filters['request_id'] = {
        '()': 'log_request_id.filters.RequestIDFilter',
    }
    _handler_filters.append('request_id')

if _use_json and _json_logger_available:
    _handlers = {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'json',
            'filters': _handler_filters,
        },
    }
    _formatters = {
        'json': {
            '()': 'pythonjsonlogger.jsonlogger.JsonFormatter',
            'format': '%(asctime)s %(name)s %(levelname)s %(message)s',
        },
    }
else:
    _handlers = {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
            'filters': _handler_filters,
        },
    }
    _formatters = {
        'verbose': {
            'format': '{levelname} {asctime} {name} {message}',
            'style': '{',
        },
    }

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'filters': _filters,
    'formatters': _formatters,
    'handlers': _handlers,
    'loggers': {
        '': {
            'handlers': ['console'],
            'level': os.getenv('DJANGO_LOG_LEVEL', 'DEBUG' if DEBUG else 'INFO'),
        },
        'django.request': {
            'handlers': ['console'],
            'level': 'WARNING',
            'propagate': False,
        },
        'environ': {
            'handlers': ['console'],
            'level': 'WARNING',
            'propagate': False,
        },
        'django_otp': {
            'handlers': ['console'],
            'level': 'DEBUG',
            'propagate': True,
        },
        'django.contrib.auth': {
            'handlers': ['console'],
            'level': 'DEBUG',
            'propagate': True,
        },
        'access': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}
