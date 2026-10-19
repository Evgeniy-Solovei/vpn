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
