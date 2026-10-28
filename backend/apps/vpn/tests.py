import base64
from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from apps.vpn.models import VPNServer, VPNKey
from apps.vpn.services import get_or_create_default_server, generate_pac_script

User = get_user_model()

class VPNTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='vpnuser',
            email='vpnuser@test.com',
            password='TestPassword123',
            balance=Decimal('20.00'),
            daily_deduction=Decimal('3.50')
        )
        self.server = get_or_create_default_server()
        self.key = VPNKey.objects.create(
            user=self.user,
            server=self.server,
            whitelist_enabled=True
        )

    def test_vless_url_structure(self):
        """VLESS Reality URL must contain required protocol parameters."""
        url = self.key.get_vless_url()
        self.assertTrue(url.startswith(f"vless://{self.key.key_uuid}@{self.server.ip}:{self.server.port}"))
        self.assertIn("security=reality", url)
        self.assertIn(f"sni={self.server.reality_sni}", url)
        self.assertIn(f"pbk={self.server.reality_pbk}", url)
        self.assertIn(f"sid={self.server.reality_short_id}", url)
        self.assertIn("flow=xtls-rprx-vision", url)

    def test_incy_and_connect_urls(self):
        """INCY and connect URLs must be properly formed."""
        incy_url = self.key.get_incy_url()
        self.assertTrue(incy_url.startswith("incy://import/"))

        connect_url = self.key.get_connect_url()
        self.assertIn(f"/vpn/connect/{self.key.sub_token}/", connect_url)

    def test_subscription_endpoint_active_user(self):
        """Active user receives base64 encoded subscription with VLESS links."""
        url = reverse('subscription', kwargs={'token': self.key.sub_token})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'text/plain; charset=utf-8')
        self.assertIn('subscription-userinfo', resp.headers)

        # Decode base64
        decoded = base64.b64decode(resp.content).decode('utf-8')
        self.assertIn(str(self.key.key_uuid), decoded)
        self.assertIn(self.server.ip, decoded)

    def test_subscription_endpoint_expired_user(self):
        """Expired or zero-balance user receives HTTP 402."""
        self.user.balance = Decimal('0.00')
        self.user.save()

        url = reverse('subscription', kwargs={'token': self.key.sub_token})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 402)
        self.assertIn("Subscription expired", resp.content.decode('utf-8'))

    def test_pac_endpoint_routing_rules(self):
        """PAC endpoint contains Russian whitelist rules when whitelist is enabled."""
        url = reverse('pac_script', kwargs={'token': self.key.sub_token})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'application/x-ns-proxy-autoconfig')
        
        content = resp.content.decode('utf-8')
        self.assertIn("gosuslugi.ru", content)
        self.assertIn("sberbank.ru", content)
        self.assertIn("*.ru", content)
        self.assertIn("DIRECT", content)

    def test_toggle_whitelist_ajax(self):
        """Authenticated user can toggle Russian whitelist status."""
        self.client.login(username='vpnuser', password='TestPassword123')
        resp = self.client.post(reverse('toggle_whitelist'))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['success'])
        self.assertFalse(data['whitelist_enabled']) # Was True, now False

        self.key.refresh_from_db()
        self.assertFalse(self.key.whitelist_enabled)

    def test_regenerate_key_ajax(self):
        """Authenticated user can regenerate their UUID key."""
        old_uuid = self.key.key_uuid
        self.client.login(username='vpnuser', password='TestPassword123')
        resp = self.client.post(reverse('regenerate_key'))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['success'])
        self.assertNotEqual(str(old_uuid), data['new_uuid'])

        self.key.refresh_from_db()
        self.assertNotEqual(self.key.key_uuid, old_uuid)

    def test_connect_landing_redirect_view(self):
        """Connect landing page loads successfully with 1-click schemes and copy buttons."""
        url = reverse('incy_connect', kwargs={'token': self.key.sub_token})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Быстрое подключение VLESS Reality")
        self.assertContains(resp, self.key.get_incy_url())

    def test_check_server_health_detects_online_status(self):
        """Mocked TCP connect marks server online and saves measured ping."""
        from unittest.mock import patch
        from apps.vpn.services import check_server_health

        with patch('socket.socket') as mock_sock_cls:
            mock_sock = mock_sock_cls.return_value
            mock_sock.connect.return_value = None

            result = check_server_health(self.server)
            self.assertTrue(result['success'])
            self.assertEqual(result['status'], 'online')
            self.assertGreater(result['ping_ms'], 0)

            self.server.refresh_from_db()
            self.assertEqual(self.server.health_status, 'online')
            self.assertIsNotNone(self.server.last_checked_at)

    def test_check_server_health_detects_rkn_blocking_on_timeout(self):
        """Socket timeout marks server blocked_rkn with timestamp."""
        import socket
        from unittest.mock import patch
        from apps.vpn.services import check_server_health

        with patch('socket.socket') as mock_sock_cls:
            mock_sock = mock_sock_cls.return_value
            mock_sock.connect.side_effect = socket.timeout("Connection timed out")

            result = check_server_health(self.server)
            self.assertFalse(result['success'])
            self.assertEqual(result['status'], 'blocked_rkn')

            self.server.refresh_from_db()
            self.assertEqual(self.server.health_status, 'blocked_rkn')
            self.assertIsNotNone(self.server.rkn_blocked_at)
            self.assertIn("Timeout", self.server.rkn_check_result)

    def test_auto_failover_migrates_banned_server_keys(self):
        """Auto-failover migrates keys away from blocked_rkn servers to healthy nodes."""
        from apps.vpn.services import failover_banned_servers

        healthy_de = VPNServer.objects.create(
            name="Germany • Frankfurt",
            country_code="DE",
            ip="194.87.100.12",
            port=443,
            ping_ms=55,
            health_status="online",
            is_active=True
        )
        banned_nl = self.server
        banned_nl.health_status = "blocked_rkn"
        banned_nl.save()

        # Key is on banned server
        self.assertEqual(self.key.server_id, banned_nl.id)

        migrated_count = failover_banned_servers()
        self.assertEqual(migrated_count, 1)

        self.key.refresh_from_db()
        self.assertEqual(self.key.server_id, healthy_de.id)

    def test_relay_server_national_shutdown_support(self):
        """Relay server represents domestic bridge node for national blackout bypass."""
        relay_ru = VPNServer.objects.create(
            name="Россия • Москва (Relay)",
            country_code="RU",
            ip="185.129.50.15",
            port=443,
            server_type="relay",
            is_emergency_relay=True,
            relay_upstream=self.server,
            ping_ms=18,
            health_status="online"
        )
        self.assertTrue(relay_ru.is_relay)
        self.assertTrue(relay_ru.is_emergency_relay)
        self.assertEqual(relay_ru.relay_upstream.id, self.server.id)

        # PAC script generation for relay server
        pac = generate_pac_script(relay_ru, whitelist_enabled=True)
        self.assertIn("185.129.50.15", pac)
        self.assertIn("DIRECT", pac)

    def test_dashboard_auto_recovers_if_current_server_is_banned(self):
        """When user visits dashboard with a banned server, their key is automatically fixed."""
        healthy_fi = VPNServer.objects.create(
            name="Finland • Helsinki",
            country_code="FI",
            ip="95.217.1.1",
            port=443,
            ping_ms=30,
            health_status="online",
            is_active=True
        )
        self.server.health_status = 'blocked_rkn'
        self.server.save()

        self.client.login(username='vpnuser', password='TestPassword123')
        resp = self.client.get(reverse('dashboard'))
        self.assertEqual(resp.status_code, 200)

        self.key.refresh_from_db()
        self.assertEqual(self.key.server_id, healthy_fi.id)

    def test_check_servers_management_command(self):
        """check_servers management command runs successfully with --mock flag."""
        from django.core.management import call_command
        from io import StringIO
        out = StringIO()
        call_command('check_servers', '--mock', stdout=out)
        output = out.getvalue()
        self.assertIn("Серверов проверено", output)

