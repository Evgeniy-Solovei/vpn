import json
import logging
import httpx
from typing import Optional, Dict, Any
from .models import VPNServer, VPNKey

logger = logging.getLogger(__name__)

# List of domains for direct routing in Russia/Belarus
DIRECT_DOMAINS = [
    # Top Level Domains
    "*.ru", "*.рф", "*.su", "*.by",
    # Government & Municipal
    "gosuslugi.ru", "*.gosuslugi.ru", "nalog.ru", "*.nalog.ru",
    "mos.ru", "*.mos.ru", "pbr.ru", "cbr.ru",
    # Russian Banks & Payments
    "sberbank.ru", "*.sberbank.ru", "sber.ru", "*.sber.ru",
    "tbank.ru", "*.tbank.ru", "tinkoff.ru", "*.tinkoff.ru",
    "vtb.ru", "*.vtb.ru", "alfabank.ru", "*.alfabank.ru",
    "gazprombank.ru", "*.gazprombank.ru", "raiffeisen.ru", "*.raiffeisen.ru",
    "mir-connect.ru", "nspk.ru", "*.nspk.ru", "sbp.nspk.ru",
    # Ecosystems & Search
    "yandex.ru", "*.yandex.ru", "ya.ru", "*.ya.ru", "yastatic.net",
    "mail.ru", "*.mail.ru", "vk.com", "*.vk.com", "vkvideo.ru", "*.vkvideo.ru",
    "ok.ru", "*.ok.ru", "dzen.ru", "*.dzen.ru",
    # E-commerce & Services
    "ozon.ru", "*.ozon.ru", "wildberries.ru", "*.wildberries.ru",
    "avito.ru", "*.avito.ru", "market.yandex.ru", "hh.ru", "*.hh.ru",
    # Streaming & Media (RF)
    "kinopoisk.ru", "*.kinopoisk.ru", "ivi.ru", "*.ivi.ru",
    "okko.tv", "*.okko.tv", "rutube.ru", "*.rutube.ru", "smotrim.ru",
]

def get_or_create_default_server() -> VPNServer:
    server = VPNServer.objects.filter(is_active=True).first()
    if not server:
        from django.conf import settings
        server = VPNServer.objects.create(
            name="Нидерланды 01 (Амстердам)",
            country_code="NL",
            country_name="Нидерланды",
            ip=getattr(settings, 'XRAY_PUBLIC_IP', '89.110.100.12') or '89.110.100.12',
            port=int(getattr(settings, 'XRAY_PUBLIC_PORT', 443) or 443),
            reality_sni=getattr(settings, 'XRAY_SNI', 'www.microsoft.com') or 'www.microsoft.com',
            reality_pbk=getattr(settings, 'XRAY_PBK', 'w4XF_zC_test_pub_key_1234567890abcdef') or 'w4XF_zC_test_pub_key_1234567890abcdef',
            reality_short_id=getattr(settings, 'XRAY_SHORT_ID', '0123456789abcdef') or '0123456789abcdef',
            ping_ms=45,
            is_active=True
        )
    return server


class ThreeXUIService:
    """Service to interact with 3X-UI / Xray API on remote VPS."""

    def __init__(self, server: VPNServer):
        self.server = server
        self.base_url = (server.panel_url or "").rstrip('/')
        self.client = httpx.Client(timeout=10.0, verify=False)
        self.cookies = {}

    def is_configured(self) -> bool:
        return bool(self.base_url and self.server.panel_password)

    def login(self) -> bool:
        if not self.is_configured():
            return False
        login_url = f"{self.base_url}/login"
        payload = {
            "username": self.server.panel_username,
            "password": self.server.panel_password
        }
        try:
            resp = self.client.post(login_url, data=payload)
            if resp.status_code == 200 and resp.json().get('success'):
                self.cookies = resp.cookies
                return True
            logger.warning(f"Failed to login to 3X-UI {self.base_url}: {resp.text}")
            return False
        except Exception as e:
            logger.error(f"Error connecting to 3X-UI at {self.base_url}: {e}")
            return False

    def add_client(self, key: VPNKey) -> bool:
        if not self.login():
            logger.info("3X-UI not configured or unreachable; using local key generation mode.")
            return True

        add_url = f"{self.base_url}/panel/api/inbounds/addClient"
        client_settings = {
            "id": str(key.key_uuid),
            "flow": "xtls-rprx-vision",
            "email": f"{key.user.username}_{key.user.id}",
            "limitIp": 2,
            "totalGB": 0,
            "expiryTime": 0,
            "enable": True,
            "tgId": key.user.telegram_id or "",
            "subId": key.sub_token
        }
        payload = {
            "id": self.server.panel_inbound_id,
            "settings": json.dumps({"clients": [client_settings]})
        }
        try:
            resp = self.client.post(add_url, json=payload, cookies=self.cookies)
            data = resp.json()
            if data.get('success'):
                logger.info(f"Successfully added client {key.user.username} to 3X-UI")
                return True
            logger.warning(f"3X-UI addClient response: {data}")
            return False
        except Exception as e:
            logger.error(f"Error calling addClient on 3X-UI: {e}")
            return False

    def delete_client(self, key: VPNKey) -> bool:
        if not self.login():
            return True
        del_url = f"{self.base_url}/panel/api/inbounds/{self.server.panel_inbound_id}/delClient/{key.key_uuid}"
        try:
            resp = self.client.post(del_url, cookies=self.cookies)
            return resp.status_code == 200
        except Exception as e:
            logger.error(f"Error deleting client on 3X-UI: {e}")
            return False


def generate_pac_script(server: VPNServer, whitelist_enabled: bool) -> str:
    """
    Generates a Proxy Auto-Config (PAC) JavaScript file.
    Enables connection without downloading applications on macOS, Windows, iOS, Android, Firefox, Chrome.
    """
    direct_domains_json = json.dumps(DIRECT_DOMAINS)
    proxy_host = f"SOCKS5 {server.ip}:1080; PROXY {server.ip}:8080; DIRECT"

    if not whitelist_enabled:
        return f"""// VPN Live Dev PAC Script - All Traffic via VPN
function FindProxyForURL(url, host) {{
    if (isPlainHostName(host) || shExpMatch(host, "*.local")) {{
        return "DIRECT";
    }}
    return "{proxy_host}";
}}
"""

    return f"""// VPN Live Dev PAC Script - Smart Direct Routing (RU / RB Bypass)
var directDomains = {direct_domains_json};

function FindProxyForURL(url, host) {{
    // Local / Intranet
    if (isPlainHostName(host) || shExpMatch(host, "*.local") || isInNet(dnsResolve(host), "10.0.0.0", "255.0.0.0") || isInNet(dnsResolve(host), "192.168.0.0", "255.255.0.0")) {{
        return "DIRECT";
    }}

    // Russian & Belarusian domains and services -> DIRECT (no VPN, avoid bank/government blocks)
    for (var i = 0; i < directDomains.length; i++) {{
        if (shExpMatch(host, directDomains[i])) {{
            return "DIRECT";
        }}
    }}

    // All other traffic (blocked sites, YouTube, Instagram, X) -> VPN Tunnel
    return "{proxy_host}";
}}
"""
