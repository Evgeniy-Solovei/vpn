import uuid
import secrets
from datetime import date, timedelta
from urllib.parse import quote
from django.db import models
from django.conf import settings
from apps.accounts.models import CustomUser

COUNTRY_FLAGS = {
    'NL': '🇳🇱',
    'DE': '🇩🇪',
    'FI': '🇫🇮',
    'SE': '🇸🇪',
    'US': '🇺🇸',
    'TR': '🇹🇷',
    'KZ': '🇰🇿',
    'PL': '🇵🇱',
    'GB': '🇬🇧',
    'RU': '🇷🇺',
    'BY': '🇧🇾',
    'FR': '🇫🇷',
    'CH': '🇨🇭',
}

class VPNServer(models.Model):
    SERVER_TYPE_CHOICES = [
        ('direct', 'Прямой зарубежный сервер'),
        ('relay', 'Мост «Белый интернет» РФ/РБ (Шатдаун)'),
    ]

    HEALTH_STATUS_CHOICES = [
        ('online', '🟢 В сети (Отличный пинг)'),
        ('degraded', '🟡 Высокий пинг (> 150 мс)'),
        ('blocked_rkn', '🔴 Заблокирован РКН / ТСПУ'),
        ('offline', '⚫ Недоступен'),
    ]

    name = models.CharField(max_length=128, verbose_name="Название сервера", default="Франция • Париж")
    server_type = models.CharField(max_length=16, choices=SERVER_TYPE_CHOICES, default='direct', verbose_name="Тип сервера")
    health_status = models.CharField(max_length=16, choices=HEALTH_STATUS_CHOICES, default='online', verbose_name="Состояние доступности")
    is_emergency_relay = models.BooleanField(default=False, verbose_name="Мост «Белый интернет» (Шатдаун)")
    relay_upstream = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL, related_name='downstream_relays', verbose_name="Выходной сервер (Relay Upstream)")

    country_code = models.CharField(max_length=4, default="FR", verbose_name="Код страны (ISO)")
    country_name = models.CharField(max_length=64, default="Франция", verbose_name="Страна")
    city = models.CharField(max_length=64, default="Париж", verbose_name="Город / Локация")
    ip = models.GenericIPAddressField(verbose_name="IP сервера", default="81.19.137.255")
    port = models.PositiveIntegerField(default=443, verbose_name="Порт VLESS Reality")
    
    # Reality Settings
    reality_sni = models.CharField(max_length=255, default="www.microsoft.com", verbose_name="SNI (Маскировка)")
    reality_pbk = models.CharField(max_length=255, default="w4XF_zC_test_pub_key_1234567890abcdef", verbose_name="Reality Public Key")
    reality_short_id = models.CharField(max_length=64, default="0123456789abcdef", verbose_name="Reality Short ID")
    reality_spider_x = models.CharField(max_length=64, default="/", verbose_name="Spider X")
    
    # 3X-UI Integration
    panel_url = models.CharField(max_length=255, blank=True, null=True, verbose_name="URL панели 3X-UI (e.g. http://ip:2053)")
    panel_username = models.CharField(max_length=64, blank=True, null=True, default="admin", verbose_name="Логин панели")
    panel_password = models.CharField(max_length=128, blank=True, null=True, verbose_name="Пароль панели")
    panel_inbound_id = models.PositiveIntegerField(default=1, verbose_name="ID Inbound в 3X-UI")

    ping_ms = models.PositiveIntegerField(default=42, verbose_name="Пинг (мс)")
    load_percent = models.PositiveIntegerField(default=24, verbose_name="Загрузка сервера (%)")
    speed_description = models.CharField(max_length=64, default="1 Gbps • Безлимит", verbose_name="Канал")
    is_active = models.BooleanField(default=True, verbose_name="Активен")
    order = models.PositiveIntegerField(default=10, verbose_name="Порядок сортировки")
    
    last_checked_at = models.DateTimeField(null=True, blank=True, verbose_name="Время последней проверки")
    rkn_blocked_at = models.DateTimeField(null=True, blank=True, verbose_name="Время блокировки РКН")
    rkn_check_result = models.CharField(max_length=255, blank=True, default="", verbose_name="Результат проверки РКН")
    created_at = models.DateTimeField(auto_now_add=True)


    class Meta:
        verbose_name = "VPN Сервер"
        verbose_name_plural = "VPN Сервера"

    @property
    def flag(self) -> str:
        return COUNTRY_FLAGS.get(self.country_code.upper().strip(), '🌐')

    @property
    def is_relay(self) -> bool:
        return self.server_type == 'relay' or self.is_emergency_relay

    @property
    def is_healthy(self) -> bool:
        return self.is_active and self.health_status in ('online', 'degraded')

    @property
    def display_name(self) -> str:
        """Красивое авто-название: 🇳🇱 Нидерланды • Амстердам"""
        city_part = f" • {self.city}" if self.city else ""
        relay_badge = " [Мост «Белый интернет»]" if self.is_relay else ""
        return f"{self.flag} {self.country_name}{city_part}{relay_badge}"

    @property
    def clean_name(self) -> str:
        city_part = f" • {self.city}" if self.city else ""
        relay_badge = " (Белый интернет)" if self.is_relay else ""
        return f"{self.country_name}{city_part}{relay_badge}"

    def mark_blocked_rkn(self, reason="TSPU handshake drop / timeout"):
        from django.utils import timezone
        self.health_status = 'blocked_rkn'
        self.rkn_blocked_at = timezone.now()
        self.rkn_check_result = reason[:250]
        self.is_active = False
        self.save(update_fields=['health_status', 'rkn_blocked_at', 'rkn_check_result', 'is_active'])

    def mark_online(self, ping: int = None):
        from django.utils import timezone
        self.health_status = 'online'
        self.last_checked_at = timezone.now()
        self.rkn_check_result = "OK"
        update_fields = ['health_status', 'last_checked_at', 'rkn_check_result']
        if ping is not None:
            self.ping_ms = ping
            update_fields.append('ping_ms')
        self.save(update_fields=update_fields)

    def save(self, *args, **kwargs):
        if not self.name or '01' in self.name or '1(0)' in self.name:
            city_part = f" • {self.city}" if self.city else ""
            self.name = f"{self.country_name}{city_part}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.display_name} ({self.ip}:{self.port}) [{self.ping_ms} ms]"



def generate_sub_token():
    return secrets.token_urlsafe(24)

def get_default_reset_date():
    return date.today() + timedelta(days=30)

class VPNKey(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='vpn_keys', verbose_name="Пользователь")
    server = models.ForeignKey(VPNServer, on_delete=models.CASCADE, related_name='keys', verbose_name="Сервер")
    key_uuid = models.UUIDField(default=uuid.uuid4, unique=True, verbose_name="UUID ключа")
    sub_token = models.CharField(max_length=64, default=generate_sub_token, unique=True, verbose_name="Токен подписки")
    
    whitelist_enabled = models.BooleanField(default=True, verbose_name="Белый список РФ (Direct Routing)")
    max_devices = models.PositiveIntegerField(default=5, verbose_name="Лимит устройств (IP)")
    is_active = models.BooleanField(default=True, verbose_name="Активен")
    
    # Fair Usage Policy (FUP) & Traffic Management (Pooled across all servers)
    used_traffic_bytes = models.BigIntegerField(default=0, verbose_name="Использованный трафик (байт)")
    traffic_limit_gb = models.PositiveIntegerField(default=150, verbose_name="Лимит скоростного трафика (ГБ)")
    traffic_reset_date = models.DateField(default=get_default_reset_date, verbose_name="Дата следующего сброса квоты")
    is_throttled = models.BooleanField(default=False, verbose_name="Скорость ограничена (FUP)")
    custom_whitelist = models.TextField(blank=True, default="", verbose_name="Пользовательские домены-исключения")

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создан")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлен")

    class Meta:
        verbose_name = "VPN Ключ"
        verbose_name_plural = "VPN Ключи"

    @property
    def used_traffic_gb(self) -> float:
        return round(self.used_traffic_bytes / (1024 ** 3), 1)

    @property
    def traffic_display(self) -> str:
        if self.used_traffic_bytes < 1024 * 1024:
            kb = round(self.used_traffic_bytes / 1024, 1)
            return f"{kb} КБ"
        elif self.used_traffic_bytes < 1024 * 1024 * 1024:
            mb = round(self.used_traffic_bytes / (1024 ** 2), 1)
            return f"{mb} МБ"
        else:
            gb = round(self.used_traffic_bytes / (1024 ** 3), 2)
            return f"{gb} ГБ"

    @property
    def traffic_percent(self) -> int:
        if not self.traffic_limit_gb:
            return 0
        return min(100, int((self.used_traffic_gb / self.traffic_limit_gb) * 100))

    @property
    def traffic_left_gb(self) -> float:
        if not self.traffic_limit_gb:
            return 0.0
        return max(0.0, round(self.traffic_limit_gb - self.used_traffic_gb, 1))

    @property
    def is_unlimited(self) -> bool:
        return self.traffic_limit_gb == 0

    @property
    def current_speed_mbps(self) -> int:
        if self.is_throttled:
            return 10
        return 500

    def check_and_update_throttle(self):
        """Auto-throttle if usage exceeds quota."""
        if self.used_traffic_gb >= self.traffic_limit_gb:
            if not self.is_throttled:
                self.is_throttled = True
                self.save(update_fields=['is_throttled'])
        else:
            if self.is_throttled:
                self.is_throttled = False
                self.save(update_fields=['is_throttled'])

    def record_traffic(self, server: VPNServer, bytes_delta: int):
        """Record traffic consumed on a specific server and update total user quota."""
        self.used_traffic_bytes += bytes_delta
        self.check_and_update_throttle()
        self.save(update_fields=['used_traffic_bytes', 'is_throttled', 'updated_at'])

        ust, _ = UserServerTraffic.objects.get_or_create(user=self.user, server=server)
        ust.bytes_used += bytes_delta
        ust.save()

    def reset_monthly_traffic(self):
        """Reset monthly traffic counters."""
        self.used_traffic_bytes = 0
        self.is_throttled = False
        self.traffic_reset_date = get_default_reset_date()
        self.save(update_fields=['used_traffic_bytes', 'is_throttled', 'traffic_reset_date', 'updated_at'])
        UserServerTraffic.objects.filter(user=self.user).update(bytes_used=0)

    def get_custom_domains(self) -> list:
        if not self.custom_whitelist:
            return []
        domains = []
        for line in self.custom_whitelist.replace(',', '\n').split('\n'):
            d = line.strip().lower()
            if d:
                if d.startswith('http://'):
                    d = d[7:]
                elif d.startswith('https://'):
                    d = d[8:]
                d = d.split('/')[0].strip()
                if d and d not in domains:
                    domains.append(d)
        return domains

    def __str__(self):
        return f"Ключ {self.user.username} @ {self.server.name} ({self.used_traffic_gb}/{self.traffic_limit_gb} GB)"


    def get_vless_url(self) -> str:
        tag = quote(f"LiveDev-{self.server.country_code}-{self.user.username}")
        # VLESS XTLS Reality Vision link
        url = (
            f"vless://{self.key_uuid}@{self.server.ip}:{self.server.port}"
            f"?type=tcp"
            f"&security=reality"
            f"&pbk={self.server.reality_pbk}"
            f"&fp=chrome"
            f"&sni={self.server.reality_sni}"
            f"&sid={self.server.reality_short_id}"
            f"&spx={quote(self.server.reality_spider_x)}"
            f"&flow=xtls-rprx-vision"
            f"#{tag}"
        )
        return url

    def get_sub_url(self) -> str:
        site_url = getattr(settings, 'SITE_URL', 'http://vpn.live-dev.by').rstrip('/')
        return f"{site_url}/sub/{self.sub_token}"

    def get_incy_url(self) -> str:
        # INCY deep link scheme format for 1-click import
        sub_url = self.get_sub_url()
        return f"incy://install-config?url={quote(sub_url)}"

    def get_hiddify_url(self) -> str:
        # Hiddify deep link scheme format
        sub_url = self.get_sub_url()
        return f"hiddify://install-config?url={quote(sub_url)}"

    def get_streisand_url(self) -> str:
        # Streisand deep link scheme format
        sub_url = self.get_sub_url()
        return f"streisand://import/{quote(sub_url)}"

    def get_v2box_url(self) -> str:
        # V2Box deep link scheme format
        sub_url = self.get_sub_url()
        return f"v2box://install-sub?url={quote(sub_url)}&name=VPN%20live-dev"

    def get_pac_url(self) -> str:
        # Proxy Auto-Config URL for in-browser usage without installing applications
        site_url = getattr(settings, 'SITE_URL', 'http://vpn.live-dev.by').rstrip('/')
        return f"{site_url}/vpn/pac/{self.sub_token}/"

    def get_connect_url(self) -> str:
        site_url = getattr(settings, 'SITE_URL', 'http://vpn.live-dev.by').rstrip('/')
        return f"{site_url}/vpn/connect/{self.sub_token}/"


class UserServerTraffic(models.Model):
    """Tracks traffic usage per user per server for multi-server aggregation."""
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='server_traffics', verbose_name="Пользователь")
    server = models.ForeignKey(VPNServer, on_delete=models.CASCADE, related_name='user_traffics', verbose_name="Сервер")
    bytes_used = models.BigIntegerField(default=0, verbose_name="Использовано на сервере (байт)")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Последняя активность")

    class Meta:
        verbose_name = "Трафик пользователя на сервере"
        verbose_name_plural = "Трафик пользователей по серверам"
        unique_together = ('user', 'server')

    @property
    def used_gb(self) -> float:
        return round(self.bytes_used / (1024 ** 3), 2)

    def __str__(self):
        return f"{self.user.username} @ {self.server.clean_name}: {self.used_gb} GB"
