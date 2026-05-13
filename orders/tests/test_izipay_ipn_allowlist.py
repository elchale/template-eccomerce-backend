"""Tests for IPN IP allowlist enforcement."""
import pytest
import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client

User = get_user_model()


def _build_ipn_payload(order_number='QLCA-TEST-0001'):
    return {
        'kr-hash': 'fake_hash_for_testing',
        'kr-hash-key': 'sha256_hmac',
        'kr-answer-type': 'V4/Payment',
        'kr-answer': json.dumps({
            'orderStatus': 'PAID',
            'orderDetails': {
                'orderId': order_number,
            },
            'transactions': [{
                'amount': 10000,
                'currency': 'PEN',
                'transactionDetails': {'cardDetails': {'legacyTransId': 'txn123'}},
                'paymentMethodType': 'CARD',
            }]
        })
    }


@pytest.mark.django_db
class TestIpnIpAllowlist:
    ipn_url = '/api/payments/izipay/ipn/'

    @patch('django.conf.settings.IZIPAY_IPN_ALLOWED_IPS', [])
    @patch('orders.views_payment.verify_hash', return_value=False)
    def test_empty_allowlist_accepts_any_ip(self, mock_verify, client):
        """With empty allowlist, any IP is accepted — IP check passes, HMAC fails → 400."""
        payload = _build_ipn_payload()
        resp = client.post(
            self.ipn_url,
            data=json.dumps(payload),
            content_type='application/json',
            REMOTE_ADDR='1.2.3.4',
        )
        # IP check passes (not 403); HMAC verification fails → 400 bad_signature
        assert resp.status_code != 403
        assert resp.status_code == 400

    @patch('django.conf.settings.IZIPAY_IPN_ALLOWED_IPS', ['10.0.0.1', '10.0.0.2'])
    def test_allowed_ip_passes_ip_check(self, client):
        """IPs in the allowlist are permitted — IP check passes, HMAC fails → 400."""
        payload = _build_ipn_payload()
        with patch('orders.views_payment.verify_hash', return_value=False):
            resp = client.post(
                self.ipn_url,
                data=json.dumps(payload),
                content_type='application/json',
                REMOTE_ADDR='10.0.0.1',
            )
        # IP check passes (not 403); HMAC verification fails → 400 bad_signature
        assert resp.status_code != 403
        assert resp.status_code == 400

    @patch('django.conf.settings.IZIPAY_IPN_ALLOWED_IPS', ['10.0.0.1'])
    def test_unknown_ip_is_blocked(self, client):
        """IPs not in the allowlist are blocked with 403."""
        payload = _build_ipn_payload()
        resp = client.post(
            self.ipn_url,
            data=json.dumps(payload),
            content_type='application/json',
            REMOTE_ADDR='9.9.9.9',
        )
        assert resp.status_code == 403
