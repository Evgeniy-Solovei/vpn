from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from apps.billing.models import TariffPlan, Transaction

User = get_user_model()

class BillingTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='billuser',
            email='billuser@test.com',
            password='TestPassword123',
            balance=Decimal('10.00'),
            autopay=False
        )
        self.client.login(username='billuser', password='TestPassword123')

    def test_tariffs_page_seeds_default_plans(self):
        """Tariffs view loads and auto-seeds default plans if empty."""
        resp = self.client.get(reverse('tariffs'))
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(TariffPlan.objects.filter(code='blackrock').exists())
        self.assertTrue(TariffPlan.objects.filter(code='blackeasy').exists())

    def test_deposit_and_balance_crediting(self):
        """Deposit creates a transaction and immediately credits user balance."""
        initial_balance = self.user.balance
        resp = self.client.post(reverse('deposit'), {
            'amount': '150',
            'payment_method': 'sbp'
        })
        self.assertEqual(resp.status_code, 302)
        self.assertRedirects(resp, reverse('dashboard'))

        self.user.refresh_from_db()
        self.assertEqual(self.user.balance, initial_balance + Decimal('150.00'))

        tx = Transaction.objects.filter(user=self.user, status='completed').first()
        self.assertIsNotNone(tx)
        self.assertEqual(tx.amount, Decimal('150.00'))
        self.assertEqual(tx.payment_method, 'sbp')

    def test_toggle_autopay(self):
        """User can toggle autopay setting via AJAX."""
        resp = self.client.post(reverse('toggle_autopay'))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['success'])
        self.assertTrue(data['autopay'])

        self.user.refresh_from_db()
        self.assertTrue(self.user.autopay)

    def test_referral_reward_5_days_on_first_payment(self):
        """When referred user makes their first payment, referrer gets 5 days free (17.50 ₽)."""
        referrer = User.objects.create_user(
            username='referrer',
            email='referrer@test.com',
            password='Password123',
            balance=Decimal('20.00'),
            daily_deduction=Decimal('3.50')
        )
        friend = User.objects.create_user(
            username='friend',
            email='friend@test.com',
            password='Password123',
            referred_by=referrer,
            balance=Decimal('10.50')
        )
        self.client.force_login(friend)

        # First deposit of 100 ₽
        self.client.post(reverse('deposit'), {'amount': '100', 'payment_method': 'mir'})

        referrer.refresh_from_db()
        # Referrer should have received +17.50 ₽ (5 days * 3.50 ₽)
        self.assertEqual(referrer.balance, Decimal('37.50'))

        # Second deposit of 50 ₽ by friend
        self.client.post(reverse('deposit'), {'amount': '50', 'payment_method': 'mir'})
        referrer.refresh_from_db()
        # Referrer should NOT receive another bonus for the second deposit
        self.assertEqual(referrer.balance, Decimal('37.50'))

    def test_promo_code_activation(self):
        """User can activate promo code once and receives bonus days."""
        from apps.billing.models import PromoCode
        promo = PromoCode.objects.create(code='TESTBONUS', days=5, max_uses=10)
        
        initial_balance = self.user.balance
        resp = self.client.post(
            reverse('billing_activate_promo'),
            data={'code': 'TESTBONUS'}
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['bonus_days'], 5)

        self.user.refresh_from_db()
        # 5 days * 3.50 ₽ = 17.50 ₽
        self.assertEqual(self.user.balance, initial_balance + Decimal('17.50'))

        # Attempt to activate again
        resp2 = self.client.post(
            reverse('billing_activate_promo'),
            data={'code': 'TESTBONUS'}
        )
        self.assertEqual(resp2.status_code, 400)
        data2 = resp2.json()
        self.assertFalse(data2['success'])
        self.assertIn('уже активировали', data2['error'])

    def test_bepaid_checkout_and_webhook(self):
        """bePaid checkout creation and webhook processing."""
        from apps.billing.models import PaymentOrder
        import json

        resp = self.client.post(reverse('bepaid_checkout'))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['success'])
        order_id = data['order_id']

        order = PaymentOrder.objects.get(order_id=order_id)
        self.assertEqual(order.status, PaymentOrder.Status.PENDING)

        # Simulate bePaid webhook
        webhook_payload = {
            "transaction": {
                "tracking_id": order_id,
                "status": "successful",
                "amount": 500,
                "currency": "BYN"
            }
        }
        initial_balance = self.user.balance
        resp_wh = self.client.post(
            reverse('bepaid_webhook'),
            data=json.dumps(webhook_payload),
            content_type='application/json'
        )
        self.assertEqual(resp_wh.status_code, 200)

        order.refresh_from_db()
        self.assertEqual(order.status, PaymentOrder.Status.PAID)
        self.user.refresh_from_db()
        self.assertEqual(self.user.balance, initial_balance + Decimal('150.00'))

    def test_promo_code_inactive_rejected(self):
        """Inactive promo codes cannot be redeemed."""
        from apps.billing.models import PromoCode
        PromoCode.objects.create(code='DISABLEDCODE', days=5, is_active=False)
        resp = self.client.post(reverse('billing_activate_promo'), {'code': 'DISABLEDCODE'})
        self.assertEqual(resp.status_code, 400)
        data = resp.json()
        self.assertFalse(data['success'])
        self.assertIn("не активен", data['error'])

    def test_promo_code_max_uses_limit_reached(self):
        """Promo codes that reached maximum uses cannot be used by new users."""
        from apps.billing.models import PromoCode
        promo = PromoCode.objects.create(code='LIMITED1', days=3, max_uses=1, used_count=1)
        resp = self.client.post(reverse('billing_activate_promo'), {'code': 'LIMITED1'})
        self.assertEqual(resp.status_code, 400)
        data = resp.json()
        self.assertFalse(data['success'])
        self.assertIn("Лимит активаций этого промокода исчерпан", data['error'])

    def test_turbo_traffic_addon_flow_and_insufficient_balance(self):
        """Purchasing extra 50 GB traffic requires at least 30 ₽ balance."""
        # Insufficient balance
        self.user.balance = Decimal('15.00')
        self.user.save()
        resp = self.client.post(reverse('api_buy_traffic'))
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(resp.json()['success'])
        self.assertIn("Недостаточно средств", resp.json()['error'])

        # Sufficient balance
        self.user.balance = Decimal('50.00')
        self.user.save()
        resp_ok = self.client.post(reverse('api_buy_traffic'))
        self.assertEqual(resp_ok.status_code, 200)
        self.assertTrue(resp_ok.json()['success'])
        self.user.refresh_from_db()
        self.assertEqual(self.user.balance, Decimal('20.00')) # 50 - 30

    def test_yookassa_checkout_creation_and_redirect(self):
        """YooKassa checkout creation creates YooKassaOrder and redirects to confirmation URL."""
        from apps.billing.models import YooKassaOrder
        resp = self.client.post(reverse('yookassa_create'), {
            'amount': '105',
            'payment_method': 'sbp'
        })
        self.assertEqual(resp.status_code, 302)
        order = YooKassaOrder.objects.filter(user=self.user).first()
        self.assertIsNotNone(order)
        self.assertEqual(order.amount_rub, Decimal('105.00'))
        self.assertEqual(order.payment_method_type, 'sbp')
        self.assertEqual(order.status, YooKassaOrder.Status.PENDING)
        self.assertIn(order.order_id, resp.url)

    def test_yookassa_checkout_json_api(self):
        """YooKassa JSON API returns checkout_url and order details."""
        import json
        from apps.billing.models import YooKassaOrder
        resp = self.client.post(
            reverse('yookassa_create'),
            data=json.dumps({'amount': 200, 'payment_method': 'mir'}),
            content_type='application/json',
            HTTP_ACCEPT='application/json'
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['success'])
        self.assertIn('checkout_url', data)
        self.assertEqual(data['amount_rub'], '200.00')

        order = YooKassaOrder.objects.get(order_id=data['order_id'])
        self.assertEqual(order.amount_rub, Decimal('200.00'))
        self.assertEqual(order.payment_method_type, 'mir')

    def test_yookassa_webhook_payment_succeeded(self):
        """YooKassa payment.succeeded webhook activates order, credits balance, and records transaction."""
        import json
        from apps.billing.models import YooKassaOrder, Transaction
        order = YooKassaOrder.objects.create(
            order_id='LD-YK-TESTWH1',
            payment_id='2d54e4df-000f-5000-8000-1d989f66085a',
            user=self.user,
            amount_rub=Decimal('105.00'),
            days=30,
            payment_method_type='sbp',
            status=YooKassaOrder.Status.PENDING
        )
        initial_balance = self.user.balance

        webhook_payload = {
            "type": "notification",
            "event": "payment.succeeded",
            "object": {
                "id": "2d54e4df-000f-5000-8000-1d989f66085a",
                "status": "succeeded",
                "amount": {"value": "105.00", "currency": "RUB"},
                "metadata": {"order_id": "LD-YK-TESTWH1"}
            }
        }
        resp = self.client.post(
            reverse('yookassa_webhook'),
            data=json.dumps(webhook_payload),
            content_type='application/json'
        )
        self.assertEqual(resp.status_code, 200)

        order.refresh_from_db()
        self.assertEqual(order.status, YooKassaOrder.Status.PAID)
        self.assertIsNotNone(order.paid_at)

        self.user.refresh_from_db()
        self.assertEqual(self.user.balance, initial_balance + Decimal('105.00'))

        tx = Transaction.objects.filter(external_id=order.payment_id, status='completed').first()
        self.assertIsNotNone(tx)
        self.assertEqual(tx.payment_method, 'yookassa')

    def test_yookassa_mock_pay_page(self):
        """YooKassa mock payment view renders summary and processes simulated payment."""
        from apps.billing.models import YooKassaOrder
        order = YooKassaOrder.objects.create(
            order_id='LD-YK-MOCK123',
            user=self.user,
            amount_rub=Decimal('105.00'),
            days=30,
            status=YooKassaOrder.Status.PENDING
        )
        # GET renders mock page
        resp_get = self.client.get(reverse('yookassa_mock_pay', args=[order.order_id]))
        self.assertEqual(resp_get.status_code, 200)
        self.assertContains(resp_get, "ЮKassa")
        self.assertContains(resp_get, "LD-YK-MOCK123")

        # POST simulates confirmation
        resp_post = self.client.post(reverse('yookassa_mock_pay', args=[order.order_id]))
        self.assertEqual(resp_post.status_code, 302)
        self.assertRedirects(resp_post, reverse('dashboard'))

        order.refresh_from_db()
        self.assertEqual(order.status, YooKassaOrder.Status.PAID)



