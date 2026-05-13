"""Core utility views: liveness / readiness probes, robots.txt."""
import logging

from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.views.decorators.cache import cache_control
from django.views.decorators.http import require_GET

logger = logging.getLogger(__name__)


@require_GET
@cache_control(no_cache=True, no_store=True)
def healthz(request):
    """Process liveness probe — always 200 if the process is running."""
    return JsonResponse({'status': 'ok'})


@require_GET
@cache_control(no_cache=True, no_store=True)
def readyz(request):
    """Dependency readiness probe — 503 if any dependency is unreachable."""
    failures = {}

    # Database ping
    try:
        from django.db import connection
        connection.ensure_connection()
    except Exception as exc:
        logger.error('readyz: database unreachable: %s', exc)
        failures['database'] = str(exc)

    # Redis ping
    try:
        from django.core.cache import cache
        cache.set('__readyz__', '1', timeout=5)
    except Exception as exc:
        logger.error('readyz: cache unreachable: %s', exc)
        failures['cache'] = str(exc)

    # Broker ping (only when Celery is in use)
    use_celery = getattr(settings, 'USE_CELERY', True)
    if use_celery:
        try:
            from kombu import Connection
            broker_url = getattr(settings, 'BROKER_URL', '')
            with Connection(broker_url) as conn:
                conn.ensure_connection(max_retries=1)
        except Exception as exc:
            logger.error('readyz: broker unreachable: %s', exc)
            failures['broker'] = str(exc)

    if failures:
        return JsonResponse({'status': 'degraded', 'failures': failures}, status=503)
    return JsonResponse({'status': 'ok'})


@require_GET
def robots_txt(request):
    """Serve robots.txt pointing crawlers to the sitemap."""
    frontend_domain = getattr(settings, 'FRONTEND_DOMAIN', '')
    lines = [
        'User-agent: *',
        'Allow: /',
        'Disallow: /admin/',
        'Disallow: /auth/',
        f'Sitemap: {frontend_domain}/sitemap.xml',
    ]
    return HttpResponse('\n'.join(lines), content_type='text/plain')
