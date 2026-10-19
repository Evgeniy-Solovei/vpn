from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from apps.vpn.models import VPNKey, VPNServer

User = get_user_model()

class AccountsTestCase(TestCase):
    def setUp(self):
        self.client = Client()

    def test_user_registration_success(self):
        """Test user registration flow, initial trial balance, and automatic VPN key creation."""
        resp = self.client.post(reverse('register'), {
            'username': 'cyberpilot',
            'email': 'pilot@test.com',
            'password': 'StrongPassword123',
            'password_confirm': 'StrongPassword123',
        })
        self.assertEqual(resp.status_code, 302)
        self.assertRedirects(resp, reverse('dashboard'))

        user = User.objects.get(username='cyberpilot')
        self.assertEqual(user.email, 'pilot@test.com')
        self.assertTrue(user.is_authenticated)
        self.assertGreater(user.balance, 0)
        self.assertTrue(len(user.referral_code) >= 6)

        # Check default key is automatically provisioned
        key = VPNKey.objects.filter(user=user).first()
        self.assertIsNotNone(key)
        self.assertTrue(key.is_active)
        self.assertTrue(key.whitelist_enabled)

    def test_duplicate_username_fails(self):
        """Registration with existing username must fail with validation error."""
        User.objects.create_user(username='existinguser', email='first@test.com', password='password123')
        resp = self.client.post(reverse('register'), {
            'username': 'existinguser',
            'email': 'second@test.com',
            'password': 'password123',
            'password_confirm': 'password123',
        })
        self.assertEqual(resp.status_code, 200)
        self.assertFormError(resp.context['form'], 'username', "Пользователь с таким логином уже существует")

    def test_duplicate_email_detection(self):
        """Duplicate email detection returns warning card for password reset."""
        User.objects.create_user(username='userone', email='duplicate@test.com', password='password123')
        resp = self.client.post(reverse('register'), {
            'username': 'usertwo',
            'email': 'duplicate@test.com',
            'password': 'password123',
            'password_confirm': 'password123',
        })
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.context['email_already_exists'])
        self.assertEqual(resp.context['existing_email'], 'duplicate@test.com')

    def test_login_with_username_and_email(self):
        """Users can log in with both username or email."""
        user = User.objects.create_user(username='testlogin', email='login@test.com', password='SecretPassword123')

        # Test login via username
        resp1 = self.client.post(reverse('login'), {
            'login': 'testlogin',
            'password': 'SecretPassword123',
        })
        self.assertEqual(resp1.status_code, 302)
        self.assertRedirects(resp1, reverse('dashboard'))

        self.client.logout()

        # Test login via email
        resp2 = self.client.post(reverse('login'), {
            'login': 'login@test.com',
            'password': 'SecretPassword123',
        })
        self.assertEqual(resp2.status_code, 302)
        self.assertRedirects(resp2, reverse('dashboard'))

    def test_user_days_left_calculation(self):
        """Verify days left calculation based on daily deduction."""
        user = User.objects.create_user(
            username='billinguser',
            email='bill@test.com',
            password='password123',
            balance=Decimal('35.00'),
            daily_deduction=Decimal('3.50')
        )
        self.assertEqual(user.days_left, 10)

        # Zero balance
        user.balance = Decimal('0.00')
        self.assertEqual(user.days_left, 0)

        # Partial balance
        user.balance = Decimal('5.00')
        self.assertEqual(user.days_left, 1)

    def test_referral_registration_bonus(self):
        """Referrer receives bonus when a new user registers with their referral code."""
        referrer = User.objects.create_user(
            username='referrer',
            email='ref@test.com',
            password='password123',
            balance=Decimal('10.00')
        )
        ref_code = referrer.referral_code

        # Register new user with ?ref=
        self.client.post(f"{reverse('register')}?ref={ref_code}", {
            'username': 'newinvited',
            'email': 'invited@test.com',
            'password': 'password123',
            'password_confirm': 'password123',
        })

        referrer.refresh_from_db()
        self.assertEqual(referrer.balance, Decimal('20.00')) # 10.00 + 10.00 bonus

    def test_password_reset_flow(self):
        """Test complete password reset flow via token."""
        user = User.objects.create_user(username='resetuser', email='reset@test.com', password='OldPassword123')

        # Request reset
        resp = self.client.post(reverse('password_reset'), {'email': 'reset@test.com'})
        self.assertEqual(resp.status_code, 302)
        self.assertRedirects(resp, reverse('password_reset_done'))

        # Generate token
        token = default_token_generator.make_token(user)
        uid = urlsafe_base64_encode(force_bytes(user.pk))

        # Confirm reset
        confirm_url = reverse('password_reset_confirm', kwargs={'uidb64': uid, 'token': token})
        resp_confirm = self.client.post(confirm_url, {
            'new_password': 'BrandNewPassword123',
            'new_password_confirm': 'BrandNewPassword123',
        })
        self.assertEqual(resp_confirm.status_code, 302)
        self.assertRedirects(resp_confirm, reverse('dashboard'))

        # Check new password works
        user.refresh_from_db()
        self.assertTrue(user.check_password('BrandNewPassword123'))

    def test_login_issues_90_day_persistent_device_key(self):
        """Login issues a 90-day persistent device key cookie and creates DeviceAuthKey record."""
        user = User.objects.create_user(username='persuser', email='pers@test.com', password='Password123!')
        from apps.accounts.models import DeviceAuthKey
        from django.conf import settings

        resp = self.client.post(reverse('login'), {
            'login': 'persuser',
            'password': 'Password123!',
            'remember_me': True,
        })
        self.assertEqual(resp.status_code, 302)
        cookie_name = getattr(settings, 'DEVICE_KEY_COOKIE_NAME', 'vpn_device_key')
        self.assertIn(cookie_name, resp.cookies)
        self.assertEqual(resp.cookies[cookie_name]['max-age'], 90 * 24 * 3600)

        # Check DB key exists and is valid
        key_val = resp.cookies[cookie_name].value
        device_key = DeviceAuthKey.objects.filter(user=user, key=key_val).first()
        self.assertIsNotNone(device_key)
        self.assertTrue(device_key.is_valid())

    def test_persistent_auth_middleware_restores_session_without_password(self):
        """User with valid 90-day device key cookie is automatically logged in on return."""
        user = User.objects.create_user(username='autoenter', email='auto@test.com', password='Password123!')
        from apps.accounts.models import DeviceAuthKey
        from django.conf import settings
        from apps.vpn.models import VPNServer, VPNKey
        from apps.vpn.services import get_or_create_default_server

        server = get_or_create_default_server()
        VPNKey.objects.get_or_create(user=user, server=server)

        device_key = DeviceAuthKey.issue_key(user, days=90)
        cookie_name = getattr(settings, 'DEVICE_KEY_COOKIE_NAME', 'vpn_device_key')

        # Create fresh client with NO existing session
        fresh_client = Client()
        fresh_client.cookies[cookie_name] = device_key.key

        # Access protected dashboard
        resp = fresh_client.get(reverse('dashboard'))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['user'].username, 'autoenter')

    def test_logout_invalidates_device_key_and_clears_cookies(self):
        """Logout deletes device key from DB and clears both cookies."""
        user = User.objects.create_user(username='logoutuser', email='logout@test.com', password='Password123!')
        from apps.accounts.models import DeviceAuthKey
        from django.conf import settings

        # Login
        self.client.post(reverse('login'), {
            'login': 'logoutuser',
            'password': 'Password123!',
            'remember_me': True,
        })
        cookie_name = getattr(settings, 'DEVICE_KEY_COOKIE_NAME', 'vpn_device_key')
        key_val = self.client.cookies[cookie_name].value
        self.assertTrue(DeviceAuthKey.objects.filter(key=key_val).exists())

        # Logout
        resp = self.client.get(reverse('logout'))
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(DeviceAuthKey.objects.filter(key=key_val).exists())
        self.assertEqual(resp.cookies[cookie_name].value, '')

    def test_expired_device_key_does_not_authenticate(self):
        """Expired device key is ignored and user is redirected to login."""
        user = User.objects.create_user(username='expireduser', email='expired@test.com', password='Password123!')
        from apps.accounts.models import DeviceAuthKey
        from django.conf import settings
        from django.utils import timezone
        from datetime import timedelta

        expired_key = DeviceAuthKey.objects.create(
            user=user,
            key='expired_test_key_123',
            expires_at=timezone.now() - timedelta(days=1)
        )
        cookie_name = getattr(settings, 'DEVICE_KEY_COOKIE_NAME', 'vpn_device_key')

        fresh_client = Client()
        fresh_client.cookies[cookie_name] = expired_key.key

        resp = fresh_client.get(reverse('dashboard'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse('login'), resp.url)

    def test_support_modal_options_present_in_base_template(self):
        """Verify support modal contains all 3 contact channels (Telegram, WhatsApp, Phone)."""
        resp = self.client.get(reverse('login'))
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode('utf-8')

        # Check Support trigger
        self.assertIn('support-modal', content)
        self.assertIn('Поддержка', content)

        # Check 3 direct redirect channels
        self.assertIn('https://t.me/livedev_by', content)
        self.assertIn('@livedev_by', content)

        self.assertIn('https://wa.me/79206612923', content)
        self.assertIn('+7 (920) 661-29-23', content)

        self.assertIn('tel:+79206612923', content)
        self.assertIn('Максим', content)


