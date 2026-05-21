"""Culqi payment gateway settings.

Culqi is the active payment gateway. It replaces Izipay; the Izipay settings
(settings/izipay.py) and code (orders/izipay.py, views_payment.py) are kept
but dormant — selectable again via PAYMENT_GATEWAY below.

Account: shared "Qolca Solutions" Culqi merchant account.
Panel:   https://culqipanel.culqi.com
API:     https://api.culqi.com/v2   ·   Docs: https://docs.culqi.com
"""
import os

# Public key (pk_test_… / pk_live_…) — safe to expose in the browser.
CULQI_PUBLIC_KEY = os.environ.get('CULQI_PUBLIC_KEY', '')

# Secret key (sk_test_… / sk_live_…) — server-side only, never expose.
CULQI_SECRET_KEY = os.environ.get('CULQI_SECRET_KEY', '')

# Random slug appended to the webhook URL path so it cannot be guessed.
# Use the same value when registering the webhook in CulqiPanel → Eventos.
CULQI_WEBHOOK_PATH_SECRET = os.environ.get('CULQI_WEBHOOK_PATH_SECRET', '')

# Culqi REST API v2 base URL. Test vs live is implied by the key prefix.
CULQI_API_URL = 'https://api.culqi.com/v2'

# Active payment gateway: 'culqi' (default) or 'izipay'. While this is 'culqi'
# the Izipay endpoints stay registered but are not exercised by the frontend.
PAYMENT_GATEWAY = os.environ.get('PAYMENT_GATEWAY', 'culqi')
