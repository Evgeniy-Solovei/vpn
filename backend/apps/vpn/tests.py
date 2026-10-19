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
        self.assertTrue(incy_url.startswith("incy://install-config?url="))

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
        """Connect landing page loads successfully with INCY scheme and copy buttons."""
        url = reverse('incy_connect', kwargs={'token': self.key.sub_token})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Подключение в приложении INCY")
        self.assertContains(resp, self.key.get_incy_url())
