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
        self.assertEqual(data['servers'][0]['country_code'], 'FR')

    def test_api_tariffs_list(self):
        """API returns active tariffs list."""
        resp = self.client.get(reverse('api_tariffs_list'))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn('plans', data)

    def test_user_profile_unauthenticated(self):
        """User profile returns authenticated: False when no session."""
        resp = self.client.get(reverse('api_user_profile'))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertFalse(data.get('authenticated'))

    def test_user_profile_authenticated(self):
        """User profile returns real user and VPN config when logged in."""
        user = User.objects.create_user(
            username='authuser',
            email='authuser@test.com',
            password='password123',
            balance=Decimal('80.00')
        )
        self.client.force_login(user)
        resp = self.client.get(reverse('api_user_profile'))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get('authenticated'))
        self.assertEqual(data['user']['username'], 'authuser')
        self.assertEqual(data['user']['balance'], 80.0)

    def test_demo_login_api(self):
        """Demo login endpoint authenticates the demo user."""
        resp = self.client.post(reverse('api_demo_login'))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get('authenticated'))
        self.assertEqual(data['user']['username'], 'demo')

    def test_buy_traffic_api(self):
        """Buy traffic increments limit by 50 GB and deducts 30 ₽."""
        user = User.objects.create_user(
            username='turbouser',
            email='turbouser@test.com',
            password='password123',
            balance=Decimal('50.00')
        )
        server = VPNServer.objects.create(name='Test Server', ip='1.2.3.4', port=443)
        VPNKey.objects.create(user=user, server=server, traffic_limit_gb=200)
        self.client.force_login(user)
        resp = self.client.post(reverse('api_buy_traffic'))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['traffic']['limit_gb'], 250)
        user.refresh_from_db()
        self.assertEqual(user.balance, Decimal('20.00'))

    def test_custom_whitelist_api(self):
        """User can save custom domains to whitelist and retrieve them."""
        user = User.objects.create_user(
            username='whitelistuser',
            email='wluser@test.com',
            password='password123'
        )
        self.client.force_login(user)
        resp = self.client.post(
            reverse('api_custom_whitelist'),
            data=json.dumps({'domains': 'https://mycompany.com/page, provider.by, test.local'}),
            content_type='application/json'
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['success'])
        self.assertIn('mycompany.com', data['custom_domains'])
        self.assertIn('provider.by', data['custom_domains'])
        self.assertIn('test.local', data['custom_domains'])

    def test_servers_list_api_excludes_blocked_rkn_and_includes_relays(self):
        """Servers list endpoint filters out RKN blocked nodes and displays relay attributes."""
        VPNServer.objects.create(
            name="Blocked Russian Server",
            country_code="RU",
            ip="1.2.3.4",
            port=443,
            health_status="blocked_rkn",
            is_active=True
        )
        relay = VPNServer.objects.create(
            name="Relay Node RU",
            country_code="RU",
            ip="185.129.50.15",
            port=443,
            server_type="relay",
            is_emergency_relay=True,
            health_status="online",
            is_active=True
        )

        resp = self.client.get(reverse('api_servers_list'))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        server_ips = [s['ip'] for s in data['servers']]
        self.assertNotIn('1.2.3.4', server_ips)
        self.assertIn('185.129.50.15', server_ips)

        relay_item = next(s for s in data['servers'] if s['ip'] == '185.129.50.15')
        self.assertTrue(relay_item['is_relay'])
        self.assertEqual(relay_item['server_type'], 'relay')

    def test_api_switch_server_flow(self):
        """User can switch their active server to an active healthy server."""
        user = User.objects.create_user(
            username='switchuser',
            email='switch@test.com',
            password='password123'
        )
        key = VPNKey.objects.create(user=user, server=self.server)
        new_server = VPNServer.objects.create(
            name="Sweden • Stockholm",
            country_code="SE",
            ip="194.87.200.5",
            port=443,
            ping_ms=40,
            health_status="online",
            is_active=True
        )

        self.client.force_login(user)

        # Successful switch
        resp = self.client.post(
            reverse('api_switch_server'),
            data=json.dumps({'server_id': new_server.id}),
            content_type='application/json'
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()['success'])
        key.refresh_from_db()
        self.assertEqual(key.server_id, new_server.id)

        # Attempt switch to blocked server
        blocked = VPNServer.objects.create(
            name="Bad Server",
            country_code="NL",
            ip="9.9.9.9",
            port=443,
            health_status="blocked_rkn",
            is_active=True
        )
        resp_bad = self.client.post(
            reverse('api_switch_server'),
            data=json.dumps({'server_id': blocked.id}),
            content_type='application/json'
        )
        self.assertEqual(resp_bad.status_code, 400)
        self.assertFalse(resp_bad.json()['success'])
        self.assertIn("недоступен", resp_bad.json()['error'])

    def test_api_deposit_flow(self):
        """Russian deposit endpoint credits user balance via SBP/MIR."""
        user = User.objects.create_user(
            username='depositguy',
            email='dep@test.com',
            password='password123',
            balance=Decimal('10.00'),
            telegram_id='777888999'
        )

        # Successful deposit
        resp = self.client.post(
            reverse('api_deposit'),
            data=json.dumps({
                'telegram_id': '777888999',
                'amount': 105,
                'payment_method': 'sbp'
            }),
            content_type='application/json'
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['success'])
        user.refresh_from_db()
        self.assertEqual(user.balance, Decimal('115.00')) # 10 + 105

        # Minimum amount validation
        resp_low = self.client.post(
            reverse('api_deposit'),
            data=json.dumps({
                'telegram_id': '777888999',
                'amount': 5,
                'payment_method': 'sbp'
            }),
            content_type='application/json'
        )
        self.assertEqual(resp_low.status_code, 400)
        self.assertFalse(resp_low.json()['success'])
        self.assertIn("Минимальная сумма", resp_low.json()['error'])




