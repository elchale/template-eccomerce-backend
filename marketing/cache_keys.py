"""
Cache key constants for the marketing app.
All keys are prefixed with 'marketing:' to avoid collisions.
TTL guidelines:
  - ACTIVE_PROMOCIONES_CACHE_KEY: 2 minutes
  - ACTIVE_BANNERS_CACHE_KEY:     5 minutes (use as prefix, append :<tipo>)
  - ACTIVE_POPUPS_CACHE_KEY:      5 minutes (use as prefix, append :<tipo>)
  - CONFIGURACION_CACHE_KEY:      10 minutes
  - SEARCH_SUGGESTIONS_CACHE_KEY: 1 minute (use as prefix, append :<query>)
  - SITE_THEME_CACHE_KEY:         30 minutes
"""

ACTIVE_PROMOCIONES_CACHE_KEY = 'marketing:active_promociones'
ACTIVE_BANNERS_CACHE_KEY = 'marketing:active_banners'
ACTIVE_POPUPS_CACHE_KEY = 'marketing:active_popups'
CONFIGURACION_CACHE_KEY = 'marketing:configuracion'
SEARCH_SUGGESTIONS_CACHE_KEY = 'marketing:search_suggestions'
SITE_THEME_CACHE_KEY = 'marketing:site_theme'
SITE_THEME_CACHE_TTL = 60 * 30  # 30 minutes
