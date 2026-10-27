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

    def test_error_incident_middleware_catches_exception_and_renders_500(self):
        """Unhandled view exceptions are intercepted, logged into ErrorIncident DB, and render 500.html."""
        from django.test import RequestFactory
        from apps.accounts.middleware import ErrorIncidentMiddleware
        from apps.accounts.models import ErrorIncident

        rf = RequestFactory()
        request = rf.get('/dashboard/')
        user = User.objects.create_user(username='erruser', email='err@test.com', password='password123')
        request.user = user

        def broken_view(req):
            raise RuntimeError("Database connection suddenly dropped during query")

        middleware = ErrorIncidentMiddleware(broken_view)
        response = None
        try:
            response = middleware(request)
        except Exception as exc:
            response = middleware.process_exception(request, exc)

        self.assertIsNotNone(response)
        self.assertEqual(response.status_code, 500)

        # Incident record created in DB
        incident = ErrorIncident.objects.filter(user=user).first()
        self.assertIsNotNone(incident)
        self.assertIn("Database connection suddenly dropped", incident.error_message)
        self.assertIn("RuntimeError", incident.traceback)
        self.assertEqual(incident.path, '/dashboard/')
        self.assertFalse(incident.is_resolved)

        content = response.content.decode('utf-8')
        self.assertIn(incident.incident_id, content)
        self.assertIn("Что-то пошло не так", content)
        self.assertIn("@livedev_by", content)

    def test_error_incident_middleware_api_json_response(self):
        """API exceptions return JSON error with incident code instead of HTML."""
        from django.test import RequestFactory
        from apps.accounts.middleware import ErrorIncidentMiddleware
        from apps.accounts.models import ErrorIncident
        import json

        rf = RequestFactory()
        request = rf.post('/api/servers/switch/', data='{"server_id": 999}', content_type='application/json')
        request.user = User.objects.create_user(username='apierruser', email='apierr@test.com', password='password123')

        def broken_api_view(req):
            raise ValueError("Invalid cryptographic key format encountered")

        middleware = ErrorIncidentMiddleware(broken_api_view)
        try:
            response = middleware(request)
        except Exception as exc:
            response = middleware.process_exception(request, exc)

        self.assertEqual(response.status_code, 500)
        data = json.loads(response.content.decode('utf-8'))
        self.assertFalse(data['success'])
        self.assertIn('incident_id', data)
        self.assertIn('@livedev_by', data['support']['telegram'])

        # DB incident matches
        incident = ErrorIncident.objects.get(incident_id=data['incident_id'])
        self.assertIn("Invalid cryptographic key", incident.error_message)

    def test_custom_404_html_and_api(self):
        """Unknown URLs redirect unauthenticated to login and authenticated to dashboard; API returns JSON 404."""
        # Anonymous web request redirects to login
        resp = self.client.get('/some-random-unknown-page-path-987/')
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/auth/login/', resp.headers.get('Location', ''))

        # Anonymous admin attempts redirect to login
        resp_admin = self.client.get('/admin/')
        self.assertEqual(resp_admin.status_code, 302)
        self.assertIn('/auth/login/', resp_admin.headers.get('Location', ''))

        # Anonymous request to secret admin path redirects to login
        from django.conf import settings
        admin_slug = getattr(settings, 'ADMIN_URL_PATH', 'management-hq').strip('/')
        resp_sec_admin = self.client.get(f'/{admin_slug}/')
        self.assertEqual(resp_sec_admin.status_code, 302)
        self.assertIn('/auth/login/', resp_sec_admin.headers.get('Location', ''))

        # Authenticated normal user request to unknown route redirects to dashboard
        normal_user = User.objects.create_user(username='normtester', email='normtester@test.com', password='PassWord123!')
        self.client.force_login(normal_user)
        resp_auth = self.client.get('/some-random-unknown-page-path-987/')
        self.assertEqual(resp_auth.status_code, 302)
        self.assertEqual(resp_auth.headers.get('Location'), '/dashboard/')

        # Authenticated normal user to secret admin is blocked and redirected to dashboard
        resp_auth_admin = self.client.get(f'/{admin_slug}/')
        self.assertEqual(resp_auth_admin.status_code, 302)
        self.assertEqual(resp_auth_admin.headers.get('Location'), '/dashboard/')

        # Superuser can access secret admin
        superuser = User.objects.create_superuser(username='supertest', email='supertest@test.com', password='PassWord123!')
        self.client.force_login(superuser)
        resp_superuser = self.client.get(f'/{admin_slug}/')
        self.assertEqual(resp_superuser.status_code, 200)

        # API 404 remains JSON
        resp_api = self.client.get('/api/some-unknown-endpoint-route/')
        self.assertEqual(resp_api.status_code, 404)
        data = resp_api.json()
        self.assertFalse(data['success'])
        self.assertEqual(data['error'], 'Not Found')

    def test_weak_password_registration_rejected(self):
        """Password shorter than 6 characters is rejected by validator."""
        resp = self.client.post(reverse('register'), {
            'username': 'shortpassuser',
            'email': 'shortpass@test.com',
            'password': '123',
            'password_confirm': '123',
        })
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(User.objects.filter(username='shortpassuser').exists())

    def test_web_registration_initial_balance_one_day(self):
        """Web registration awards 1 free day (3.50 ₽) initially."""
        resp = self.client.post(reverse('register'), {
            'username': 'onedayuser',
            'email': 'oneday@test.com',
            'password': 'password123',
            'password_confirm': 'password123',
        })
        self.assertEqual(resp.status_code, 302)
        user = User.objects.get(username='onedayuser')
        self.assertEqual(user.balance, Decimal('3.50'))
        self.assertEqual(user.days_left, 1)
        self.assertFalse(user.telegram_bonus_claimed)

    def test_telegram_link_code_and_claiming_bonus(self):
        """Linking Telegram awards +2 free days (total 3 days = 10.50 ₽)."""
        user = User.objects.create_user(
            username='webuser1',
            email='webuser1@test.com',
            password='password123',
            balance=Decimal('3.50')
        )
        self.client.force_login(user)

        # 1. Generate link code
        resp = self.client.get(reverse('telegram_link_code'))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['success'])
        code = data['code']

        # 2. Link account via Telegram Bot API
        import json
        link_resp = self.client.post(
            reverse('api_tg_link_account'),
            data=json.dumps({
                'code': code,
                'telegram_id': '888777666',
                'telegram_username': 'cool_tg_user'
            }),
            content_type='application/json'
        )
        self.assertEqual(link_resp.status_code, 200)
        link_data = link_resp.json()
        self.assertTrue(link_data['success'])
        self.assertTrue(link_data['bonus_awarded'])
        self.assertEqual(link_data['new_balance'], 10.50)
        self.assertEqual(link_data['days_left'], 3)

        user.refresh_from_db()
        self.assertEqual(user.telegram_id, '888777666')
        self.assertEqual(user.telegram_username, 'cool_tg_user')
        self.assertTrue(user.telegram_bonus_claimed)

        # 3. Duplicate Telegram link rejected for another user
        user2 = User.objects.create_user(
            username='webuser2',
            email='webuser2@test.com',
            password='password123',
            balance=Decimal('3.50')
        )
        self.client.force_login(user2)
        resp2 = self.client.get(reverse('telegram_link_code'))
        code2 = resp2.json()['code']

        dup_resp = self.client.post(
            reverse('api_tg_link_account'),
            data=json.dumps({
                'code': code2,
                'telegram_id': '888777666',
                'telegram_username': 'cool_tg_user'
            }),
            content_type='application/json'
        )
        self.assertEqual(dup_resp.status_code, 400)
        self.assertFalse(dup_resp.json()['success'])

    def test_magic_login_token(self):
        """Magic login token provides instant 1-click passwordless entry."""
        user = User.objects.create_user(
            username='magicuser',
            email='magic@test.com',
            password='password123',
            telegram_id='555444333'
        )
        import json
        # 1. Bot calls generate magic link
        gen_resp = self.client.post(
            reverse('api_tg_generate_magic_link'),
            data=json.dumps({'telegram_id': '555444333'}),
            content_type='application/json'
        )
        self.assertEqual(gen_resp.status_code, 200)
        login_url = gen_resp.json()['login_url']
        token = login_url.rstrip('/').split('/')[-1]

        # 2. Browser opens magic link
        resp = self.client.get(reverse('magic_login', kwargs={'token': token}))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('dashboard'))

        # User is authenticated
        self.assertEqual(int(self.client.session['_auth_user_id']), user.id)

    def test_telegram_auth_callback(self):
        """Telegram widget authorization logs in existing user or creates new."""
        import hmac
        import hashlib
        from django.conf import settings

        bot_token = getattr(settings, 'BOT_TOKEN', '') or 'test_bot_token'
        with self.settings(BOT_TOKEN=bot_token):
            auth_data = {
                'id': '987654321',
                'first_name': 'TestTelegram',
                'username': 'tg_tester',
                'auth_date': '1700000000',
            }
            data_check = [f"{k}={v}" for k, v in sorted(auth_data.items())]
            data_check_string = "\n".join(data_check)
            secret_key = hashlib.sha256(bot_token.encode()).digest()
            auth_data['hash'] = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

            resp = self.client.get(reverse('telegram_auth_callback'), auth_data)
            self.assertEqual(resp.status_code, 302)
            self.assertEqual(resp.url, reverse('dashboard'))

            created = User.objects.get(telegram_id='987654321')
            self.assertEqual(created.telegram_username, 'tg_tester')
            self.assertEqual(int(self.client.session['_auth_user_id']), created.id)

    def test_google_login_redirect_without_client_id(self):
        """When GOOGLE_CLIENT_ID is empty, redirects to login with informative message."""
        with self.settings(GOOGLE_CLIENT_ID=''):
            resp = self.client.get(reverse('google_login'))
            self.assertEqual(resp.status_code, 302)
            self.assertEqual(resp.url, reverse('login'))

    def test_google_login_redirect_with_client_id(self):
        """When GOOGLE_CLIENT_ID is configured, redirects to accounts.google.com."""
        with self.settings(GOOGLE_CLIENT_ID='mock-google-client-id-123'):
            resp = self.client.get(reverse('google_login'))
            self.assertEqual(resp.status_code, 302)
            self.assertIn('accounts.google.com/o/oauth2/v2/auth', resp.url)
            self.assertIn('client_id=mock-google-client-id-123', resp.url)
            self.assertTrue(self.client.session.get('google_oauth_state'))

    def test_google_callback_flow(self):
        """Mocked Google code exchange logs in or creates new user with 3-day trial."""
        from unittest.mock import patch, MagicMock

        session = self.client.session
        session['google_oauth_state'] = 'mockstate123'
        session.save()

        with self.settings(GOOGLE_CLIENT_ID='mock-id', GOOGLE_CLIENT_SECRET='mock-secret'):
            token_json = b'{"access_token": "mock_access_token_xyz"}'
            userinfo_json = b'{"sub": "google_uid_999", "email": "googler@example.com", "name": "Google Tester"}'

            with patch('urllib.request.urlopen') as mock_urlopen:
                mock_resp1 = MagicMock()
                mock_resp1.read.return_value = token_json
                mock_resp1.__enter__.return_value = mock_resp1

                mock_resp2 = MagicMock()
                mock_resp2.read.return_value = userinfo_json
                mock_resp2.__enter__.return_value = mock_resp2

                mock_urlopen.side_effect = [mock_resp1, mock_resp2]

                resp = self.client.get(reverse('google_callback'), {'code': 'auth_code_123', 'state': 'mockstate123'})
                self.assertEqual(resp.status_code, 302)
                self.assertEqual(resp.url, reverse('dashboard'))

                created = User.objects.get(google_id='google_uid_999')
                self.assertEqual(created.email, 'googler@example.com')
                self.assertEqual(int(self.client.session['_auth_user_id']), created.id)

    def test_merge_users_service(self):
        """merge_users combines balances, keys, and telegram data into the target user."""
        from apps.accounts.services import merge_users
        from apps.vpn.models import VPNKey
        from apps.vpn.services import get_or_create_default_server

        server = get_or_create_default_server()
        target = User.objects.create_user(username='webmaster', email='web@example.com', password='pass', balance=Decimal('10.00'))
        source = User.objects.create_user(username='tg_555', email='tg_555@live-dev.by', telegram_id='555666', telegram_username='tgmaster', balance=Decimal('50.00'))
        key_source = VPNKey.objects.create(user=source, server=server)

        merged = merge_users(target_user=target, source_user=source)
        self.assertEqual(merged.id, target.id)
        self.assertEqual(merged.balance, Decimal('60.00'))
        self.assertEqual(merged.telegram_id, '555666')
        self.assertEqual(merged.telegram_username, 'tgmaster')
        self.assertFalse(User.objects.filter(username='tg_555').exists())

        key_source.refresh_from_db()
        self.assertEqual(key_source.user_id, target.id)

    def test_tg_link_account_api_merges_duplicate_bot_account(self):
        """API tg/link-account/ successfully merges when telegram_id is already in DB."""
        import json
        from apps.accounts.models import TelegramLinkCode
        target = User.objects.create_user(username='webuser12', email='web12@example.com', password='pass', balance=Decimal('5.00'))
        source = User.objects.create_user(username='tg_99887711', email='tg_99887711@live-dev.by', telegram_id='99887711', telegram_username='telebotter', balance=Decimal('20.00'))
        source.set_unusable_password()
        source.save()
        
        link_code = TelegramLinkCode.create_for_user(target)
        payload = {
            'code': link_code.code,
            'telegram_id': '99887711',
            'telegram_username': 'telebotter'
        }
        resp = self.client.post('/api/tg/link-account/', data=json.dumps(payload), content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get('success'))

        target.refresh_from_db()
        self.assertEqual(target.telegram_id, '99887711')
        self.assertEqual(target.telegram_username, 'telebotter')
        # 5.00 + 20.00 + 7.00 (bonus) = 32.00
        self.assertEqual(target.balance, Decimal('32.00'))
        self.assertFalse(User.objects.filter(username='tg_99887711').exists())

    def test_expired_balance_deactivates_vpn_access(self):
        """When user balance reaches 0, VPN access is revoked and keys are marked inactive."""
        from datetime import date, timedelta
        from apps.vpn.models import VPNKey, VPNServer
        from apps.vpn.services import get_or_create_default_server

        server = get_or_create_default_server()
        user = User.objects.create_user(
            username='expuser',
            email='exp@test.com',
            password='password123',
            balance=Decimal('3.50'),
            daily_deduction=Decimal('3.50'),
            last_billed_date=date.today() - timedelta(days=1)
        )
        key = VPNKey.objects.create(user=user, server=server, is_active=True)
        self.assertTrue(user.has_active_subscription)
        self.assertTrue(key.is_active)

        # Apply deduction -> balance becomes 0.00
        days = user.apply_daily_deductions()
        self.assertEqual(days, 1)
        user.refresh_from_db()
        key.refresh_from_db()
        self.assertEqual(user.balance, Decimal('0.00'))
        self.assertFalse(user.has_active_subscription)
        self.assertFalse(key.is_active)

        # Ensure topup restores active subscription and syncs VPN access
        from apps.billing.models import Transaction
        tx = Transaction.objects.create(
            user=user,
            amount=Decimal('105.00'),
            payment_method='sbp',
            status='pending'
        )
        tx.complete()
        user.refresh_from_db()
        key.refresh_from_db()
        self.assertEqual(user.balance, Decimal('105.00'))
        self.assertTrue(user.has_active_subscription)
        self.assertTrue(key.is_active)




