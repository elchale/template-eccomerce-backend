"""Read store-wide config values from ``marketing.ConfiguracionTienda`` in templates.

Usage::

    {% load site_config %}
    <img src="{% site_config 'site_logo_url' %}">
    {% site_config 'social_facebook' as fb %}
    {% if fb %}<a href="{{ fb }}">…</a>{% endif %}

Values are read in bulk and cached for ten minutes (same key the public API
uses, so a single admin PATCH invalidates the cache for everyone). The cache
is populated lazily on first access per process, so an offline / no-DB email
render path falls back to ``default``.
"""
from django import template
from django.core.cache import cache

from marketing.cache_keys import CONFIGURACION_CACHE_KEY

register = template.Library()

CONFIG_CACHE_TTL = 60 * 10  # match marketing API cache


def _load_config_map() -> dict:
    cached = cache.get(CONFIGURACION_CACHE_KEY)
    if cached is not None:
        return cached

    # Local import keeps this module safe to import before app-registry init
    # (e.g. when Django collects template tags during settings load).
    from marketing.models import ConfiguracionTienda

    try:
        config = dict(ConfiguracionTienda.objects.values_list('clave', 'valor'))
    except Exception:
        # DB unreachable (e.g. during management command bootstrap) — render
        # with empty values rather than blowing up the template.
        return {}

    cache.set(CONFIGURACION_CACHE_KEY, config, CONFIG_CACHE_TTL)
    return config


@register.simple_tag
def site_config(key: str, default: str = '') -> str:
    """Return ``ConfiguracionTienda[key]`` or ``default`` if unset/blank."""
    value = _load_config_map().get(key)
    return value if value else default
