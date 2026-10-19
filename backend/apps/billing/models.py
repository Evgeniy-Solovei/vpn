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
        """Mark as completed and credit user balance."""
        if self.status != 'completed':
            self.status = 'completed'
            self.user.balance += self.amount
            self.user.save()
            self.save()

    def __str__(self):
        return f"Платёж #{self.id} — {self.user.username} ({self.amount} ₽, {self.status})"
