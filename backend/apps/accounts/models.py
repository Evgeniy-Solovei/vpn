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
    
    balance = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('10.50'), verbose_name="Баланс (₽) [3 дня теста]")
    daily_deduction = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal('3.50'), verbose_name="Ежедневное списание (₽)")
    autopay = models.BooleanField(default=True, verbose_name="Автоплатеж (автоматическое списание)")
    
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


class DeviceAuthKey(models.Model):
    """
    Persistent Device Key (90-day cached authentication).
    Allows users to stay logged in across browser sessions without entering password.
    """
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='device_keys', verbose_name="Пользователь")
    key = models.CharField(max_length=64, unique=True, db_index=True, verbose_name="Ключ устройства")
    user_agent = models.CharField(max_length=256, blank=True, verbose_name="User Agent")
    ip_address = models.GenericIPAddressField(null=True, blank=True, verbose_name="IP адрес")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    expires_at = models.DateTimeField(verbose_name="Действует до")

    class Meta:
        verbose_name = "Ключ устройства (90 дней)"
        verbose_name_plural = "Ключи устройств (90 дней)"
        ordering = ['-created_at']

    def is_valid(self) -> bool:
        from django.utils import timezone
        return timezone.now() < self.expires_at

    @classmethod
    def issue_key(cls, user, request=None, days=90):
        from django.utils import timezone
        from datetime import timedelta
        raw_key = secrets.token_urlsafe(40)
        ua = ''
        ip = None
        if request:
            ua = request.META.get('HTTP_USER_AGENT', '')[:250]
            ip = request.META.get('REMOTE_ADDR')
        return cls.objects.create(
            user=user,
            key=raw_key,
            user_agent=ua,
            ip_address=ip,
            expires_at=timezone.now() + timedelta(days=days)
        )

    def __str__(self):
        return f"Ключ для {self.user.username} (до {self.expires_at.strftime('%Y-%m-%d')})"


class ErrorIncident(models.Model):
    """
    Records unhandled server errors (500) with a unique incident code for quick debugging
    and user support.
    """
    incident_id = models.CharField(max_length=32, unique=True, db_index=True, verbose_name="Код инцидента")
    error_message = models.CharField(max_length=255, verbose_name="Ошибка")
    traceback = models.TextField(verbose_name="Стек ошибки (Traceback)")
    path = models.CharField(max_length=255, verbose_name="URL запроса")
    method = models.CharField(max_length=10, default="GET", verbose_name="Метод")
    user = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='incidents', verbose_name="Пользователь")
    ip_address = models.GenericIPAddressField(null=True, blank=True, verbose_name="IP адрес")
    user_agent = models.CharField(max_length=256, blank=True, verbose_name="User-Agent")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Время ошибки")
    is_resolved = models.BooleanField(default=False, verbose_name="Исправлено")

    class Meta:
        verbose_name = "Инцидент / Ошибка 500"
        verbose_name_plural = "Журнал ошибок (Инциденты)"
        ordering = ['-created_at']

    @classmethod
    def create_incident(cls, request, exception, tb_str=""):
        from datetime import datetime
        code = f"ERR-{secrets.token_hex(3).upper()}-{datetime.now().strftime('%Y%m%d')}"
        user = request.user if getattr(request, 'user', None) and request.user.is_authenticated else None
        ip = request.META.get('REMOTE_ADDR')
        ua = request.META.get('HTTP_USER_AGENT', '')[:250]
        return cls.objects.create(
            incident_id=code,
            error_message=str(exception)[:250],
            traceback=tb_str,
            path=request.path[:250],
            method=request.method[:10],
            user=user,
            ip_address=ip,
            user_agent=ua
        )

    def __str__(self):
        return f"[{self.incident_id}] {self.error_message} ({self.path})"


