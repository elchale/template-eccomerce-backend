from .env import env

# CORS Configuration
DEBUG = env('DEBUG', default=False)

CORS_ALLOWED_ORIGINS = [
    f"https://{env('DOMAIN', default='localhost')}",
    f"https://{env('FRONTEND_DOMAIN', default='localhost')}",
]

if DEBUG:
    CORS_ALLOWED_ORIGINS.extend(
        [
            f"http://{env('DOMAIN', default='localhost')}",
            f"http://{env('FRONTEND_DOMAIN', default='localhost')}",
        ]
    )

# Add additional CORS origins from environment variable if needed
# Set ADDITIONAL_CORS_ORIGINS in .env as comma-separated list
# Example: ADDITIONAL_CORS_ORIGINS=https://app.example.com,https://www.example.com
additional_origins = env('ADDITIONAL_CORS_ORIGINS', default='')
if additional_origins:
    from urllib.parse import urlparse
    from .common import ALLOWED_HOSTS
    for origin in additional_origins.split(','):
        origin = origin.strip()
        if not origin:
            continue
        parsed = urlparse(origin)
        if parsed.scheme and parsed.netloc:
            CORS_ALLOWED_ORIGINS.append(origin)
            ALLOWED_HOSTS.append(parsed.netloc)
        else:
            ALLOWED_HOSTS.append(origin)

# Allow credentials to be included in CORS requests (for JWT cookies if needed)
CORS_ALLOW_CREDENTIALS = True

# Headers our frontend attaches on every request (axios interceptor in
# `lib/axios.ts`) that aren't in django-cors-headers' default allowlist.
#   - Accept-Language: drives `LocaleMiddleware` -> django-modeltranslation.
#   - X-Request-Id:    distributed-tracing correlation id; echoed back by the
#                      RequestIdMiddleware in `core/middleware.py`.
# Without these, the browser preflight 200s but Access-Control-Allow-Headers
# omits them, so Chrome aborts the actual XHR with net::ERR_FAILED.
from corsheaders.defaults import default_headers

CORS_ALLOW_HEADERS = (
    *default_headers,
    'accept-language',
    'x-request-id',
)

# Expose the request-id back to the frontend so it can log it alongside
# error toasts (helps cross-reference backend logs in Sentry / log aggregator).
CORS_EXPOSE_HEADERS = ['x-request-id']
