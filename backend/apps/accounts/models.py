import secrets
import string
from decimal import Decimal
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.translation import gettext_lazy as _

def generate_ref_code():
    chars = string.ascii_uppercase + string.digits
    return ''.join(secrets.choice(chars) for _ in range(8))

class CustomUser(AbstractUser):
    email = models.EmailField(_('email address'), unique=True)
    telegram_id = models.CharField(max_length=64, blank=True, null=True, unique=True, verbose_name="Telegram ID")
    telegram_username = models.CharField(max_length=128, blank=True, null=True, verbose_name="Telegram Username")
    
    balance = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('15.00'), verbose_name="Баланс (₽)")
    daily_deduction = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal('3.50'), verbose_name="Ежедневное списание (₽)")
    autopay = models.BooleanField(default=False, verbose_name="Автоплатеж")
    
    referral_code = models.CharField(max_length=16, unique=True, blank=True, verbose_name="Реферальный код")
    referred_by = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='referrals', verbose_name="Кто пригласил")
    
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата регистрации")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    class Meta:
        verbose_name = "Пользователь"
        verbose_name_plural = "Пользователи"
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if not self.referral_code:
            code = generate_ref_code()
            while CustomUser.objects.filter(referral_code=code).exists():
                code = generate_ref_code()
            self.referral_code = code
        super().save(*args, **kwargs)

    @property
    def days_left(self) -> int:
        if self.daily_deduction <= 0:
            return 999
        if self.balance <= 0:
            return 0
        return int(self.balance // self.daily_deduction)

    @property
    def has_active_subscription(self) -> bool:
        return self.balance > 0

    def __str__(self):
        return f"{self.username} ({self.email})"
