from .env import env
from .common import DEBUG

from django.core.exceptions import ImproperlyConfigured

REDIS = {
    'host': env('REDIS_HOST'),
    'port': env('REDIS_PORT', default=6379),
    'pwd': env('REDIS_PASS', default=''),
}

if not DEBUG and str(REDIS['host']).strip().lower() in {'localhost', '127.0.0.1', '::1'}:
    raise ImproperlyConfigured('REDIS_HOST must be an external Redis host (not localhost).')

REDIS_CACHE_NAME = 'redis'

if DEBUG:
    # Dev: avoid depending on an external Redis (free-tier client caps,
    # network flakiness). Local-memory cache is per-process which is fine
    # for a single-worker runserver.
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'default',
        },
        REDIS_CACHE_NAME: {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'redis-compat',
        },
    }
else:
    CACHES = {
        'default': {
            'BACKEND': 'backend.cache.PrefixedRedisCache',
            'LOCATION': 'redis://' + REDIS['host'] + ':' + str(REDIS['port']) + '/0',
            'OPTIONS': {
                'PASSWORD': REDIS['pwd'],
                'CLIENT_CLASS': 'django_redis.client.DefaultClient',
            },
        },
        REDIS_CACHE_NAME: {
            'BACKEND': 'backend.cache.PrefixedRedisCache',
            'LOCATION': 'redis://' + REDIS['host'] + ':' + str(REDIS['port']) + '/0',
            'OPTIONS': {
                'PASSWORD': REDIS['pwd'],
                'CLIENT_CLASS': 'django_redis.client.DefaultClient',
            },
        },
    }

CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels_redis.core.RedisChannelLayer',
        'CONFIG': {
            'hosts': [
                (f"redis://:{REDIS['pwd']}@{REDIS['host']}:{REDIS['port']}/0",)
                if REDIS['pwd'] else
                (REDIS['host'], REDIS['port'])
            ],
        },
    }
}
