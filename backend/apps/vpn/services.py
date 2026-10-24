import os
import json
import logging
import re
import socket
import time
import httpx
from typing import Optional, Dict, Any
from django.db import models
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
    server = VPNServer.objects.filter(is_active=True).order_by('order', 'id').first()
    if not server:
        from django.conf import settings
        server = VPNServer.objects.create(
            name="Нидерланды • Амстердам",
            country_code="NL",
            country_name="Нидерланды",
            city="Амстердам",
            ip=getattr(settings, 'XRAY_PUBLIC_IP', '89.110.100.12') or '89.110.100.12',
            port=int(getattr(settings, 'XRAY_PUBLIC_PORT', 443) or 443),
            reality_sni=getattr(settings, 'XRAY_SNI', 'www.microsoft.com') or 'www.microsoft.com',
            reality_pbk=getattr(settings, 'XRAY_PBK', 'w4XF_zC_test_pub_key_1234567890abcdef') or 'w4XF_zC_test_pub_key_1234567890abcdef',
            reality_short_id=getattr(settings, 'XRAY_SHORT_ID', '0123456789abcdef') or '0123456789abcdef',
            ping_ms=42,
            load_percent=24,
            speed_description="1 Gbps • Безлимит",
            is_active=True
        )
    return server


class ThreeXUIService:
    """Service to interact with 3X-UI / Xray API on remote VPS."""

    def __init__(self, server: VPNServer):
        self.server = server
        self.base_url = (server.panel_url or "").rstrip('/')
        self.client = httpx.Client(timeout=10.0, verify=False, follow_redirects=True)
        self.cookies = {}
        self.csrf_token = ""

    def is_configured(self) -> bool:
        return bool(self.base_url and self.server.panel_password)

    def login(self) -> bool:
        if not self.is_configured():
            return False

        # Pre-fetch CSRF token if modern 3X-UI
        headers = {}
        try:
            get_resp = self.client.get(f"{self.base_url}/")
            csrf_match = re.search(r'meta name=["\']csrf-token["\'] content=["\']([^"\']+)["\']', get_resp.text)
            if csrf_match:
                self.csrf_token = csrf_match.group(1)
                headers['X-Csrf-Token'] = self.csrf_token
        except Exception as e:
            logger.debug(f"Could not pre-fetch CSRF token from {self.base_url}: {e}")

        login_url = f"{self.base_url}/login"
        payload = {
            "username": self.server.panel_username,
            "password": self.server.panel_password
        }
        try:
            resp = self.client.post(login_url, json=payload, headers=headers)
            if resp.status_code != 200 or not resp.json().get('success'):
                resp = self.client.post(login_url, data=payload, headers=headers)

            if resp.status_code == 200 and resp.json().get('success'):
                self.cookies = dict(resp.cookies)
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

        headers = {}
        if self.csrf_token:
            headers['X-Csrf-Token'] = self.csrf_token

        tg_id = 0
        if key.user.telegram_id:
            try:
                tg_id = int(str(key.user.telegram_id).strip())
            except (ValueError, TypeError):
                tg_id = 0

        client_settings = {
            "id": str(key.key_uuid),
            "flow": "xtls-rprx-vision",
            "email": f"{key.user.username}_{key.user.id}",
            "limitIp": getattr(key, 'max_devices', 5) or 5,
            "totalGB": 0,
            "expiryTime": 0,
            "enable": True,
            "tgId": tg_id,
            "subId": key.sub_token
        }

        # 1. Try modern 3X-UI v3.x+ API (/panel/api/clients/add)
        modern_payload = {
            "client": client_settings,
            "inboundIds": [self.server.panel_inbound_id]
        }
        try:
            resp = self.client.post(f"{self.base_url}/panel/api/clients/add", json=modern_payload, cookies=self.cookies, headers=headers)
            if resp.status_code == 200 and resp.json().get('success'):
                logger.info(f"Successfully added client {key.user.username} to 3X-UI (modern API)")
                return True
        except Exception as e:
            logger.debug(f"Modern 3X-UI clients/add failed, falling back: {e}")

        # 2. Fallback to legacy inbounds/addClient
        legacy_payload = {
            "id": self.server.panel_inbound_id,
            "settings": json.dumps({"clients": [client_settings]})
        }
        try:
            resp = self.client.post(f"{self.base_url}/panel/api/inbounds/addClient", json=legacy_payload, cookies=self.cookies, headers=headers)
            if resp.status_code == 200 and resp.json().get('success'):
                logger.info(f"Successfully added client {key.user.username} to 3X-UI (legacy API)")
                return True
            logger.warning(f"3X-UI addClient response: {resp.text}")
            return False
        except Exception as e:
            logger.error(f"Error calling addClient on 3X-UI: {e}")
            return False

    def delete_client(self, key: VPNKey) -> bool:
        if not self.login():
            return True
        headers = {}
        if self.csrf_token:
            headers['X-Csrf-Token'] = self.csrf_token

        email = f"{key.user.username}_{key.user.id}"
        # 1. Try modern 3X-UI API
        try:
            resp = self.client.post(f"{self.base_url}/panel/api/clients/del/{email}", cookies=self.cookies, headers=headers)
            if resp.status_code == 200 and resp.json().get('success'):
                return True
        except Exception:
            pass

        # 2. Fallback to legacy
        del_url = f"{self.base_url}/panel/api/inbounds/{self.server.panel_inbound_id}/delClient/{key.key_uuid}"
        try:
            resp = self.client.post(del_url, cookies=self.cookies, headers=headers)
            return resp.status_code == 200
        except Exception as e:
            logger.error(f"Error deleting client on 3X-UI: {e}")
            return False


def generate_pac_script(server: VPNServer, whitelist_enabled: bool, custom_domains: list = None) -> str:
    """
    Generates a Proxy Auto-Config (PAC) JavaScript file.
    Enables connection without downloading applications on macOS, Windows, iOS, Android, Firefox, Chrome.
    """
    combined_domains = list(DIRECT_DOMAINS) if whitelist_enabled else []
    if custom_domains:
        for d in custom_domains:
            clean = d.strip().lower()
            if clean:
                if not clean.startswith("*."):
                    combined_domains.append(f"*.{clean}")
                combined_domains.append(clean)

    direct_domains_json = json.dumps(combined_domains)
    proxy_host = f"SOCKS5 {server.ip}:1080; PROXY {server.ip}:8080; DIRECT"

    if not whitelist_enabled and not custom_domains:
        return f"""// VPN live-dev PAC Script - All Traffic via VPN
function FindProxyForURL(url, host) {{
    if (isPlainHostName(host) || shExpMatch(host, "*.local")) {{
        return "DIRECT";
    }}
    return "{proxy_host}";
}}
"""

    return f"""// VPN live-dev PAC Script - Smart Direct Routing with Custom Whitelist
var directDomains = {direct_domains_json};

function FindProxyForURL(url, host) {{
    // Local / Intranet
    if (isPlainHostName(host) || shExpMatch(host, "*.local") || isInNet(dnsResolve(host), "10.0.0.0", "255.0.0.0") || isInNet(dnsResolve(host), "192.168.0.0", "255.255.0.0")) {{
        return "DIRECT";
    }}

    // Direct domains (RU/BY banks & user custom whitelist) -> DIRECT (no VPN)
    for (var i = 0; i < directDomains.length; i++) {{
        if (shExpMatch(host, directDomains[i])) {{
            return "DIRECT";
        }}
    }}

    // All other traffic (blocked sites, YouTube, Instagram, X) -> VPN Tunnel
    return "{proxy_host}";
}}
"""


def check_server_health(server: VPNServer, timeout: float = 2.5) -> dict:
    """
    Measures TCP ping/latency to VPNServer and detects network drops / RKN blocking.
    """
    from django.utils import timezone
    t_start = time.perf_counter()
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect((server.ip, server.port))
        sock.close()
        elapsed_ms = max(5, int((time.perf_counter() - t_start) * 1000))
        server.mark_online(ping=elapsed_ms)
        logger.info(f"Server {server.clean_name} ({server.ip}:{server.port}) is ONLINE, ping: {elapsed_ms}ms")
        return {'success': True, 'status': 'online', 'ping_ms': elapsed_ms}
    except socket.timeout:
        # Typical TSPU / RKN behavior: packet drop resulting in timeout
        server.mark_blocked_rkn(reason="Timeout (TSPU / RKN packet drop)")
        logger.warning(f"Server {server.clean_name} ({server.ip}:{server.port}) TIMED OUT -> marked blocked_rkn")
        return {'success': False, 'status': 'blocked_rkn', 'error': 'Timeout'}
    except Exception as e:
        server.health_status = 'offline'
        server.last_checked_at = timezone.now()
        server.rkn_check_result = str(e)[:250]
        server.save(update_fields=['health_status', 'last_checked_at', 'rkn_check_result'])
        logger.warning(f"Server {server.clean_name} offline: {e}")
        return {'success': False, 'status': 'offline', 'error': str(e)}


def failover_banned_servers() -> int:
    """
    Auto-failover: if any user keys are linked to an inactive or blocked_rkn server,
    migrate them automatically to the best available healthy server.
    """
    banned_keys = VPNKey.objects.filter(
        models.Q(server__is_active=False) | models.Q(server__health_status='blocked_rkn')
    )
    if not banned_keys.exists():
        return 0

    healthy_server = VPNServer.objects.filter(
        is_active=True,
        health_status__in=['online', 'degraded']
    ).order_by('ping_ms').first()

    if not healthy_server:
        logger.critical("NO HEALTHY VPN SERVERS AVAILABLE FOR FAILOVER!")
        return 0

    count = 0
    for key in banned_keys:
        old_server = key.server
        key.server = healthy_server
        key.save(update_fields=['server', 'updated_at'])
        count += 1
        logger.warning(f"AUTO-FAILOVER: Migrated user {key.user.username} from {old_server.clean_name} to {healthy_server.clean_name}")

    return count


def check_all_servers_health_and_failover() -> dict:
    """
    Checks all servers, updates statuses, and triggers failover if necessary.
    """
    results = {}
    servers = VPNServer.objects.all()
    for s in servers:
        results[s.id] = check_server_health(s)
    migrated_count = failover_banned_servers()
    return {
        'servers_checked': len(results),
        'results': results,
        'migrated_users_count': migrated_count
    }


def sync_traffic_from_3xui() -> int:
    """
    Syncs real traffic statistics from 3X-UI SQLite for all clients into VPNKey.
    Reads directly from /etc/x-ui/x-ui.db on Linux server.
    """
    import sqlite3
    db_path = '/etc/x-ui/x-ui.db'
    if not os.path.exists(db_path):
        return 0

    try:
        conn = sqlite3.connect(db_path, timeout=5)
        cur = conn.cursor()
        cur.execute("SELECT email, up, down FROM client_traffics")
        rows = cur.fetchall()
        conn.close()
    except Exception as e:
        logger.warning(f"Could not read client_traffics: {e}")
        return 0

    updated = 0
    for email, up, down in rows:
        total_bytes = (up or 0) + (down or 0)
        parts = email.rsplit('_', 1)
        key = None
        if len(parts) == 2 and parts[1].isdigit():
            user_id = int(parts[1])
            key = VPNKey.objects.filter(user_id=user_id).first()
        if not key:
            key = VPNKey.objects.filter(user__username=email).first()

        if key and key.used_traffic_bytes != total_bytes:
            key.used_traffic_bytes = total_bytes
            key.check_and_update_throttle()
            key.save(update_fields=['used_traffic_bytes', 'is_throttled', 'updated_at'])
            updated += 1

    return updated


def sync_key_traffic(key: VPNKey):
    """Sync traffic for a single key from 3X-UI SQLite."""
    import sqlite3
    db_path = '/etc/x-ui/x-ui.db'
    if not os.path.exists(db_path) or not key or not getattr(key, 'user', None):
        return
    email = f"{key.user.username}_{key.user.id}"
    try:
        conn = sqlite3.connect(db_path, timeout=2)
        cur = conn.cursor()
        cur.execute("SELECT up, down FROM client_traffics WHERE email=?", (email,))
        row = cur.fetchone()
        conn.close()
        if row:
            total = (row[0] or 0) + (row[1] or 0)
            if key.used_traffic_bytes != total:
                key.used_traffic_bytes = total
                key.save(update_fields=['used_traffic_bytes', 'updated_at'])
    except Exception as e:
        logger.debug(f"Error syncing key traffic: {e}")


def ensure_key_in_panel(key: VPNKey):
    """Ensures client key UUID is registered in 3X-UI inbound on the server."""
    if not key or not key.server or not key.server.panel_url:
        return False
    try:
        svc = ThreeXUIService(key.server)
        return svc.add_client(key)
    except Exception as e:
        logger.debug(f"Error in ensure_key_in_panel: {e}")
        return False


def sync_all_keys_to_panel() -> int:
    """Ensures all active keys are registered in their servers' 3X-UI inbound."""
    synced = 0
    for key in VPNKey.objects.filter(is_active=True).select_related('server', 'user'):
        if key.server and key.server.panel_url:
            if ensure_key_in_panel(key):
                synced += 1
    return synced



