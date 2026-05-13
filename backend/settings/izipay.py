"""Izipay / Lyra payment gateway settings.

Picks the active API key and HMAC key based on IZIPAY_MODE.
Same REST API URL for TEST and PRODUCTION — credentials determine the mode.
"""
import os

IZIPAY_SHOP_ID = os.environ.get('IZIPAY_SHOP_ID', '')
IZIPAY_MODE = os.environ.get('IZIPAY_MODE', 'TEST')  # 'TEST' or 'PRODUCTION'

IZIPAY_API_KEY_TEST = os.environ.get('IZIPAY_API_KEY_TEST', '')
IZIPAY_API_KEY_PROD = os.environ.get('IZIPAY_API_KEY_PROD', '')
IZIPAY_HMAC_KEY_TEST = os.environ.get('IZIPAY_HMAC_KEY_TEST', '')
IZIPAY_HMAC_KEY_PROD = os.environ.get('IZIPAY_HMAC_KEY_PROD', '')

# Derived: select active key based on mode
IZIPAY_API_KEY = IZIPAY_API_KEY_PROD if IZIPAY_MODE == 'PRODUCTION' else IZIPAY_API_KEY_TEST
IZIPAY_HMAC_KEY = IZIPAY_HMAC_KEY_PROD if IZIPAY_MODE == 'PRODUCTION' else IZIPAY_HMAC_KEY_TEST

# Same URL for both modes — credentials determine test vs production
IZIPAY_API_URL = 'https://api.micuentaweb.pe/api-payment/V4/'

# Trust X-Forwarded-For header for source IP (True only when behind proxy/CDN)
TRUST_PROXY = os.environ.get('TRUST_PROXY', 'False').lower() == 'true'

# Comma-separated list of Izipay server IPs allowed to send IPNs. Empty = no restriction.
IZIPAY_IPN_ALLOWED_IPS = [
    ip.strip()
    for ip in os.environ.get('IZIPAY_IPN_ALLOWED_IPS', '').split(',')
    if ip.strip()
]
