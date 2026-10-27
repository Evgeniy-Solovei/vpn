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
    telegram_bonus_claimed = models.BooleanField(default=False, verbose_name="Бонус за привязку Telegram начислен")
    google_id = models.CharField(max_length=128, blank=True, null=True, unique=True, verbose_name="Google ID")
    
    balance = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('3.50'), verbose_name="Баланс (₽) [1 день теста]")
    daily_deduction = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal('3.50'), verbose_name="Ежедневное списание (₽)")
    autopay = models.BooleanField(default=True, verbose_name="Автоплатеж (автоматическое списание)")
    last_billed_date = models.DateField(null=True, blank=True, verbose_name="Дата последнего списания")
    
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

    def sync_vpn_access(self):
        """
        Synchronizes user's VPN access state across all servers.
        If subscription is active: marks keys active and provisions them in 3X-UI with calculated expiryTime.
        If subscription is expired: marks keys inactive and removes them from all 3X-UI panels immediately.
        """
        try:
            from apps.vpn.services import ensure_key_in_all_active_servers
            is_valid = self.has_active_subscription
            for key in self.vpn_keys.all():
                if key.is_active != is_valid:
                    key.is_active = is_valid
                    key.save(update_fields=['is_active'])
                ensure_key_in_all_active_servers(key)
        except Exception:
            pass

    def apply_daily_deductions(self) -> int:
        """
        Calculates elapsed calendar days since last_billed_date and deducts daily fee.
        If balance reaches 0, deactivates VPN keys and disconnects from 3X-UI.
        Returns number of days charged.
        """
        from datetime import date
        today = date.today()
        last_date = self.last_billed_date or (self.created_at.date() if self.created_at else today)

        days_passed = (today - last_date).days
        if days_passed <= 0:
            if not self.last_billed_date:
                self.last_billed_date = last_date
                self.save(update_fields=['last_billed_date'])
            if self.balance <= Decimal('0.00'):
                self.sync_vpn_access()
            return 0

        total_charge = Decimal(days_passed) * (self.daily_deduction or Decimal('3.50'))
        old_balance = self.balance
        new_balance = max(Decimal('0.00'), old_balance - total_charge)
        self.balance = new_balance
        self.last_billed_date = today
        self.save(update_fields=['balance', 'last_billed_date', 'updated_at'])

        # Record billing deduction transaction
        try:
            from apps.billing.models import Transaction
            Transaction.objects.create(
                user=self,
                amount=-total_charge,
                payment_method='sbp',
                status='completed',
                description=f"Ежедневная оплата VPN ({days_passed} дн. по {self.daily_deduction} ₽)"
            )
        except Exception:
            pass

        # Sync VPN access across all panels (cuts off if balance <= 0, updates expiryTime if balance > 0)
        self.sync_vpn_access()

        return days_passed

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


class TelegramLinkCode(models.Model):
    """
    Temporary authorization code for linking a Web account to a Telegram account
    to claim the +2 days bonus and synchronize keys.
    """
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='tg_link_codes', verbose_name="Пользователь")
    code = models.CharField(max_length=32, unique=True, db_index=True, verbose_name="Код привязки")
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(verbose_name="Действует до")

    class Meta:
        verbose_name = "Код привязки Telegram"
        verbose_name_plural = "Коды привязки Telegram"
        ordering = ['-created_at']

    def is_valid(self) -> bool:
        from django.utils import timezone
        return timezone.now() < self.expires_at

    @classmethod
    def create_for_user(cls, user, minutes=30):
        from django.utils import timezone
        from datetime import timedelta
        cls.objects.filter(user=user).delete()
        code = secrets.token_hex(8)  # 16-character alphanumeric code
        return cls.objects.create(
            user=user,
            code=code,
            expires_at=timezone.now() + timedelta(minutes=minutes)
        )

    def __str__(self):
        return f"LinkCode {self.code} -> {self.user.username}"


class MagicLoginToken(models.Model):
    """
    Temporary single-use token generated by the Telegram bot to allow
    instant, passwordless login to the website dashboard from a desktop browser.
    """
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='magic_tokens', verbose_name="Пользователь")
    token = models.CharField(max_length=48, unique=True, db_index=True, verbose_name="Токен входа")
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(verbose_name="Действует до")

    class Meta:
        verbose_name = "Одноразовый токен входа"
        verbose_name_plural = "Одноразовые токены входа"
        ordering = ['-created_at']

    def is_valid(self) -> bool:
        from django.utils import timezone
        return timezone.now() < self.expires_at

    @classmethod
    def create_for_user(cls, user, minutes=15):
        from django.utils import timezone
        from datetime import timedelta
        cls.objects.filter(user=user).delete()
        raw_token = secrets.token_urlsafe(32)
        return cls.objects.create(
            user=user,
            token=raw_token,
            expires_at=timezone.now() + timedelta(minutes=minutes)
        )

    def __str__(self):
        return f"MagicToken {self.token[:8]}... -> {self.user.username}"



