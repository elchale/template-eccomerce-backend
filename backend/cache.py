import redis

from django.conf import settings

from django_redis.cache import RedisCache

class PrefixedRedisCache(RedisCache):
    """
    Prefixed cache with init from settings
    """

    @classmethod
    def get_cache(cls, prefix: str) -> RedisCache:
        params = settings.CACHES.get(settings.REDIS_CACHE_NAME, {})
        params['KEY_PREFIX'] = prefix
        location = params.get('LOCATION', '')
        return cls(server=location, params=params)


pool = redis.ConnectionPool(
    host=settings.REDIS['host'],
    port=settings.REDIS['port'],
    db=0,
    password=(settings.REDIS.get('pwd') or None),
    socket_connect_timeout=getattr(settings, 'REDIS_SOCKET_CONNECT_TIMEOUT', None),
    socket_timeout=getattr(settings, 'REDIS_SOCKET_TIMEOUT', None),
)

redis_client = redis.Redis(
    connection_pool=pool,
)
