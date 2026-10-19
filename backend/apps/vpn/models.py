import uuid
import secrets
from urllib.parse import quote
from django.db import models
from django.conf import settings
from apps.accounts.models import CustomUser

class VPNServer(models.Model):
    name = models.CharField(max_length=128, verbose_name="Название сервера", default="Нидерланды 01")
    country_code = models.CharField(max_length=4, default="NL", verbose_name="Код страны")
    country_name = models.CharField(max_length=64, default="Нидерланды", verbose_name="Страна")
    ip = models.GenericIPAddressField(verbose_name="IP сервера", default="89.110.100.12")
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

    ping_ms = models.PositiveIntegerField(default=45, verbose_name="Пинг (мс)")
    is_active = models.BooleanField(default=True, verbose_name="Активен")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "VPN Сервер"
        verbose_name_plural = "VPN Сервера"

    def __str__(self):
        return f"{self.name} [{self.country_code}] ({self.ip}:{self.port})"


def generate_sub_token():
    return secrets.token_urlsafe(24)

class VPNKey(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='vpn_keys', verbose_name="Пользователь")
    server = models.ForeignKey(VPNServer, on_delete=models.CASCADE, related_name='keys', verbose_name="Сервер")
    key_uuid = models.UUIDField(default=uuid.uuid4, unique=True, verbose_name="UUID ключа")
    sub_token = models.CharField(max_length=64, default=generate_sub_token, unique=True, verbose_name="Токен подписки")
    
    whitelist_enabled = models.BooleanField(default=True, verbose_name="Белый список РФ (Direct Routing)")
    is_active = models.BooleanField(default=True, verbose_name="Активен")
    
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создан")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлен")

    class Meta:
        verbose_name = "VPN Ключ"
        verbose_name_plural = "VPN Ключи"

    def __str__(self):
        return f"Ключ {self.user.username} @ {self.server.name}"

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
