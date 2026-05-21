"""Mercado Pago payment gateway settings.

Mercado Pago is the ACTIVE payment gateway, replacing Culqi (which itself
replaced Izipay). Both Culqi and Izipay settings are kept but dormant —
selectable again by flipping PAYMENT_GATEWAY below.

Account: shared "Qolca Solutions" Mercado Pago merchant account.
Panel:   https://www.mercadopago.com.pe/developers/panel
API:     https://api.mercadopago.com   ·   Docs: https://www.mercadopago.com.pe/developers
"""
import os

# Public key (APP_USR-… / TEST-…) — safe to expose in the browser.
MERCADOPAGO_PUBLIC_KEY = os.environ.get('MERCADOPAGO_PUBLIC_KEY', '')

# Access token (APP_USR-… / TEST-…) — server-side only, never expose.
MERCADOPAGO_ACCESS_TOKEN = os.environ.get('MERCADOPAGO_ACCESS_TOKEN', '')

# OAuth client credentials — reserved for marketplace/OAuth flows; not used
# by the Card Payment Brick path but kept here so the env block matches the
# MP panel and so future features can opt in without a settings change.
MERCADOPAGO_CLIENT_ID = os.environ.get('MERCADOPAGO_CLIENT_ID', '')
MERCADOPAGO_CLIENT_SECRET = os.environ.get('MERCADOPAGO_CLIENT_SECRET', '')

# Webhook secret used to verify x-signature on incoming notifications.
# Source: MP panel → Tu integración → Webhooks → "Clave secreta".
MERCADOPAGO_WEBHOOK_SECRET = os.environ.get('MERCADOPAGO_WEBHOOK_SECRET', '')

# Mercado Pago REST API base URL. Test vs live is implied by the token prefix.
MERCADOPAGO_API_URL = 'https://api.mercadopago.com'

# Active payment gateway: 'mercadopago' (default), 'culqi' or 'izipay'.
# While this is 'mercadopago' the Culqi and Izipay endpoints stay registered
# but are not exercised by the frontend.
PAYMENT_GATEWAY = os.environ.get('PAYMENT_GATEWAY', 'mercadopago')
