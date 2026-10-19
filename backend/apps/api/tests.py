import json
from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from apps.vpn.models import VPNServer, VPNKey
from apps.vpn.services import get_or_create_default_server

User = get_user_model()

class ApiTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        self.server = get_or_create_default_server()

    def test_tg_sync_creates_new_user_and_provision_key(self):
        """Telegram sync creates a new user, gives trial balance, and generates key."""
        payload = {
            'telegram_id': '987654321',
            'telegram_username': 'telepilot',
            'ref_code': None
        }
        resp = self.client.post(
            reverse('api_tg_sync'),
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['success'])
        self.assertTrue(data['is_new'])
        self.assertEqual(data['user']['telegram_id'], '987654321')
        self.assertGreater(data['user']['balance'], 0)

        # Check VPN details
        self.assertIn('vless://', data['vpn']['vless_url'])
        self.assertIn('/vpn/connect/', data['vpn']['connect_url'])
        self.assertIn('/sub/', data['vpn']['sub_url'])

    def test_tg_sync_with_referral_code(self):
        """Telegram sync awards referrer bonus when ref_code is provided."""
        referrer = User.objects.create_user(
            username='mainref',
            email='mainref@test.com',
            password='password123',
            balance=Decimal('10.00')
        )
        ref_code = referrer.referral_code

        payload = {
            'telegram_id': '555444333',
            'telegram_username': 'invitedguy',
            'ref_code': ref_code
        }
        resp = self.client.post(
            reverse('api_tg_sync'),
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(resp.status_code, 200)

        referrer.refresh_from_db()
        self.assertEqual(referrer.balance, Decimal('20.00'))

    def test_api_toggle_whitelist_by_telegram_id(self):
        """Telegram bot can toggle whitelist for user via API."""
        user = User.objects.create_user(
            username='tguser',
            email='tguser@test.com',
            password='password123',
            telegram_id='11223344'
        )
        key = VPNKey.objects.create(user=user, server=self.server, whitelist_enabled=True)

        resp = self.client.post(
            reverse('api_toggle_whitelist'),
            data=json.dumps({'telegram_id': '11223344'}),
            content_type='application/json'
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['success'])
        self.assertFalse(data['whitelist_enabled'])

        key.refresh_from_db()
        self.assertFalse(key.whitelist_enabled)

    def test_api_servers_list(self):
        """API returns active servers list."""
        resp = self.client.get(reverse('api_servers_list'))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn('servers', data)
        self.assertGreater(len(data['servers']), 0)
        self.assertEqual(data['servers'][0]['country_code'], 'NL')

    def test_api_tariffs_list(self):
        """API returns active tariffs list."""
        resp = self.client.get(reverse('api_tariffs_list'))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn('plans', data)
