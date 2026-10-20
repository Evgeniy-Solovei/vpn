from decimal import Decimal
from django.db import models
from apps.accounts.models import CustomUser

class TariffPlan(models.Model):
    name = models.CharField(max_length=64, verbose_name="Название тарифа")
    code = models.CharField(max_length=32, unique=True, verbose_name="Код тарифа")
    daily_price = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal('3.50'), verbose_name="Цена в день (₽)")
    speed_mbps = models.PositiveIntegerField(default=100, verbose_name="Скорость канала (Мб/с)")
    description = models.TextField(verbose_name="Описание")
    is_featured = models.BooleanField(default=False, verbose_name="Популярный")
    is_active = models.BooleanField(default=True, verbose_name="Активен")

    class Meta:
        verbose_name = "Тарифный план"
        verbose_name_plural = "Тарифные планы"
        ordering = ['daily_price']

    def __str__(self):
        return f"{self.name} ({self.daily_price} ₽/день, {self.speed_mbps} Мб/с)"


class Transaction(models.Model):
    PAYMENT_METHODS = [
        ('sbp', 'СБП (Система быстрых платежей)'),
        ('mir', 'Банковская карта МИР'),
        ('yookassa', 'ЮKassa (СБП / Карты РФ / SberPay / T-Pay)'),
        ('bepaid', 'bePaid (Карты РБ / ЕРИП / МИР)'),
        ('tpay', 'T-Pay'),
        ('sberpay', 'SberPay'),
        ('crypto', 'Криптовалюта (USDT / TON)'),
    ]

    STATUS_CHOICES = [
        ('pending', 'Ожидает оплаты'),
        ('completed', 'Успешно оплачен'),
        ('failed', 'Ошибка / Отклонен'),
    ]

    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='transactions', verbose_name="Пользователь")
    amount = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Сумма (₽)")
    payment_method = models.CharField(max_length=32, choices=PAYMENT_METHODS, default='sbp', verbose_name="Способ оплаты")
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='pending', verbose_name="Статус")
    external_id = models.CharField(max_length=128, blank=True, null=True, verbose_name="ID в платежной системе")
    description = models.CharField(max_length=255, blank=True, default="Пополнение баланса", verbose_name="Назначение")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создана")

    class Meta:
        verbose_name = "Транзакция"
        verbose_name_plural = "Транзакции"
        ordering = ['-created_at']

    def complete(self):
        """Mark as completed and credit user balance. Awards 5 free days to referrer on first payment."""
        if self.status != 'completed':
            self.status = 'completed'
            self.user.balance += self.amount
            self.user.save()
            self.save()

            # Referral reward: 5 days free to referrer upon first real payment
            if self.user.referred_by:
                completed_count = Transaction.objects.filter(user=self.user, status='completed').count()
                if completed_count == 1:
                    referrer = self.user.referred_by
                    bonus_days = Decimal('5')
                    daily_price = referrer.daily_deduction or Decimal('3.50')
                    bonus_rub = bonus_days * daily_price
                    referrer.balance += bonus_rub
                    referrer.save(update_fields=['balance'])

    def __str__(self):
        return f"Платёж #{self.id} — {self.user.username} ({self.amount} ₽, {self.status})"


class PromoCode(models.Model):
    """
    Promotional codes for bonus subscription days (e.g. 3, 5, 10 days)
    for marketing or bug compensation.
    """
    code = models.CharField(max_length=32, unique=True, verbose_name="Промокод")
    days = models.PositiveIntegerField(default=3, verbose_name="Бонусные дни")
    max_uses = models.PositiveIntegerField(default=1000, verbose_name="Максимум активаций")
    used_count = models.PositiveIntegerField(default=0, verbose_name="Использовано раз")
    is_active = models.BooleanField(default=True, verbose_name="Активен")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создан")
    users = models.ManyToManyField(CustomUser, blank=True, related_name='used_promocodes', verbose_name="Использовавшие пользователи")

    class Meta:
        verbose_name = "Промокод"
        verbose_name_plural = "Промокоды"

    def can_be_used_by(self, user: CustomUser) -> tuple:
        if not self.is_active:
            return False, "Промокод не активен"
        if self.used_count >= self.max_uses:
            return False, "Лимит активаций этого промокода исчерпан"
        if self.users.filter(id=user.id).exists():
            return False, "Вы уже активировали этот промокод"
        return True, ""

    def activate_for(self, user: CustomUser) -> Decimal:
        daily_price = user.daily_deduction or Decimal('3.50')
        bonus_rub = Decimal(self.days) * daily_price
        user.balance += bonus_rub
        user.save(update_fields=['balance'])
        self.users.add(user)
        self.used_count += 1
        self.save(update_fields=['used_count'])
        return bonus_rub

    def __str__(self):
        return f"{self.code} (+{self.days} дн., {self.used_count}/{self.max_uses})"


class PaymentOrder(models.Model):
    """
    bePaid Checkout Orders (Belarus, Belkart, ERIP, CIS Cards).
    """
    class Status(models.TextChoices):
        PENDING = 'pending', 'Ожидает оплаты'
        PAID = 'paid', 'Оплачен'
        FAILED = 'failed', 'Отклонен'

    order_id = models.CharField(max_length=64, unique=True, verbose_name="ID Заказа")
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='bepaid_orders', verbose_name="Пользователь")
    amount_byn = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('5.00'), verbose_name="Сумма (BYN)")
    amount_rub = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('150.00'), verbose_name="Сумма (RUB)")
    days = models.PositiveIntegerField(default=30, verbose_name="Дней подписки")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING, verbose_name="Статус")
    bepaid_checkout_url = models.URLField(max_length=500, blank=True, verbose_name="Ссылка на оплату bePaid")
    bepaid_token = models.CharField(max_length=255, blank=True, verbose_name="Токен bePaid")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создан")
    paid_at = models.DateTimeField(null=True, blank=True, verbose_name="Оплачен")

    class Meta:
        verbose_name = "Заказ bePaid (РБ)"
        verbose_name_plural = "Заказы bePaid (РБ)"
        ordering = ['-created_at']

    def complete_payment(self):
        if self.status != self.Status.PAID:
            from django.utils import timezone
            self.status = self.Status.PAID
            self.paid_at = timezone.now()
            self.user.balance += self.amount_rub
            self.user.save(update_fields=['balance'])
            self.save(update_fields=['status', 'paid_at'])

            # Record corresponding transaction
            tx = Transaction.objects.create(
                user=self.user,
                amount=self.amount_rub,
                payment_method='bepaid',
                status='completed',
                external_id=self.order_id,
                description=f"Оплата подписки через bePaid ({self.amount_byn} BYN / {self.days} дн.)"
            )
            # Check referral reward (5 days)
            if self.user.referred_by:
                completed_count = Transaction.objects.filter(user=self.user, status='completed').count()
                if completed_count == 1:
                    referrer = self.user.referred_by
                    bonus_days = Decimal('5')
                    daily_price = referrer.daily_deduction or Decimal('3.50')
                    referrer.balance += bonus_days * daily_price
                    referrer.save(update_fields=['balance'])

    def __str__(self):
        return f"Заказ {self.order_id} ({self.user.username}, {self.amount_byn} BYN, {self.status})"


class YooKassaOrder(models.Model):
    """
    YooKassa Checkout Orders (Russia, Self-employed, SBP, MIR/Cards, SberPay, T-Pay).
    Official YooKassa API v3 integration with automated fiscal receipt support for self-employed.
    """
    class Status(models.TextChoices):
        PENDING = 'pending', 'Ожидает оплаты'
        PAID = 'paid', 'Оплачен'
        CANCELED = 'canceled', 'Отменен'

    order_id = models.CharField(max_length=64, unique=True, verbose_name="ID Заказа")
    payment_id = models.CharField(max_length=64, blank=True, verbose_name="ID платежа ЮKassa")
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='yookassa_orders', verbose_name="Пользователь")
    amount_rub = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('105.00'), verbose_name="Сумма (RUB)")
    days = models.PositiveIntegerField(default=30, verbose_name="Дней подписки")
    payment_method_type = models.CharField(max_length=32, default='sbp', verbose_name="Метод оплаты")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING, verbose_name="Статус")
    confirmation_url = models.URLField(max_length=500, blank=True, verbose_name="Ссылка на оплату ЮKassa")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создан")
    paid_at = models.DateTimeField(null=True, blank=True, verbose_name="Оплачен")

    class Meta:
        verbose_name = "Заказ ЮKassa (РФ)"
        verbose_name_plural = "Заказы ЮKassa (РФ)"
        ordering = ['-created_at']

    def complete_payment(self):
        if self.status != self.Status.PAID:
            from django.utils import timezone
            self.status = self.Status.PAID
            self.paid_at = timezone.now()
            self.user.balance += self.amount_rub
            self.user.save(update_fields=['balance'])
            self.save(update_fields=['status', 'paid_at'])

            # Record corresponding transaction
            tx = Transaction.objects.create(
                user=self.user,
                amount=self.amount_rub,
                payment_method='yookassa',
                status='completed',
                external_id=self.payment_id or self.order_id,
                description=f"Оплата через ЮKassa ({self.amount_rub} ₽ / {self.days} дн. • {self.payment_method_type.upper()})"
            )

            # Referral reward (5 days)
            if self.user.referred_by:
                completed_count = Transaction.objects.filter(user=self.user, status='completed').count()
                if completed_count == 1:
                    referrer = self.user.referred_by
                    bonus_days = Decimal('5')
                    daily_price = referrer.daily_deduction or Decimal('3.50')
                    referrer.balance += bonus_days * daily_price
                    referrer.save(update_fields=['balance'])

    def __str__(self):
        return f"ЮKassa {self.order_id} ({self.user.username}, {self.amount_rub} ₽, {self.status})"


