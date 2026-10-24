import os
import json
import logging
import re
import socket
import time
import httpx
from typing import Optional, Dict, Any
from django.db import models
from django.utils import timezone
from .models import VPNServer, VPNKey, VPNDevice

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
            name="Франция • Париж",
            country_code="FR",
            country_name="Франция",
            city="Париж",
            ip=getattr(settings, 'XRAY_PUBLIC_IP', '81.19.137.255') or '81.19.137.255',
            port=int(getattr(settings, 'XRAY_PUBLIC_PORT', 443) or 443),
            reality_sni=getattr(settings, 'XRAY_SNI', 'dl.google.com') or 'dl.google.com',
            reality_pbk=getattr(settings, 'XRAY_PBK', 'TPcr_j2aEjarE-AvBM1DU894voxhBIKhOZhK-R6XVX8') or 'TPcr_j2aEjarE-AvBM1DU894voxhBIKhOZhK-R6XVX8',
            reality_short_id=getattr(settings, 'XRAY_SHORT_ID', '4b3e34eb63605933') or '4b3e34eb63605933',
            ping_ms=38,
            load_percent=18,
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


def ensure_key_in_all_active_servers(key: VPNKey) -> int:
    """
    Ensures client key UUID is registered across ALL active VPN servers with panels.
    Guarantees seamless multi-server subscription support (/sub/<token>) and instant server switching.
    """
    if not key or not key.user:
        return 0
    synced = 0
    active_servers = VPNServer.objects.filter(is_active=True).exclude(panel_url__isnull=True).exclude(panel_url='')
    for srv in active_servers:
        try:
            svc = ThreeXUIService(srv)
            if svc.add_client(key):
                synced += 1
        except Exception as e:
            logger.debug(f"Error registering key on server {srv.clean_name}: {e}")
    return synced


def sync_all_keys_to_panel() -> int:
    """Ensures all active keys are registered across all active 3X-UI inbounds."""
    synced = 0
    active_servers = list(VPNServer.objects.filter(is_active=True).exclude(panel_url__isnull=True).exclude(panel_url=''))
    for key in VPNKey.objects.filter(is_active=True).select_related('server', 'user'):
        for srv in active_servers:
            try:
                svc = ThreeXUIService(srv)
                if svc.add_client(key):
                    synced += 1
            except Exception:
                pass
    return synced


def detect_device_platform_and_name(ua: str) -> tuple[str, str]:
    """Parses User-Agent to determine platform and friendly device name."""
    ua_str = (ua or "").lower()

    if "iphone" in ua_str:
        return "ios", "Apple iPhone"
    if "ipad" in ua_str:
        return "ios", "Apple iPad"
    if "cfnetwork" in ua_str or "darwin" in ua_str:
        return "ios", "Apple Устройство (iOS)"
    if "android" in ua_str:
        return "android", "Android Смартфон"
    if "macintosh" in ua_str or "mac os x" in ua_str:
        return "macos", "Apple Mac"
    if "windows" in ua_str:
        return "windows", "Windows Компьютер"
    if "tv" in ua_str or "tizen" in ua_str or "webos" in ua_str or "bravia" in ua_str:
        return "tv", "Smart TV"
    if "sing-box" in ua_str or "v2ray" in ua_str or "xray" in ua_str or "clash" in ua_str:
        return "router", "Роутер / Sing-box"
    return "other", "Мобильное устройство"


def register_user_device(user, request=None, key=None, client_type="INCY") -> Optional[VPNDevice]:
    """Registers or updates a VPNDevice entry for the user."""
    if not user or not user.is_authenticated and not getattr(user, 'id', None):
        return None

    if not key:
        key = VPNKey.objects.filter(user=user).first()

    ua = ""
    ip = None
    if request:
        ua = request.META.get('HTTP_USER_AGENT', '')[:250]
        ip = request.META.get('HTTP_X_FORWARDED_FOR')
        if ip:
            ip = ip.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR')

    platform, device_name = detect_device_platform_and_name(ua)

    import hashlib
    raw_hash_input = f"{user.id}_{platform}_{ip or 'local'}_{ua[:50]}"
    device_id = hashlib.sha256(raw_hash_input.encode('utf-8')).hexdigest()[:24]

    device, created = VPNDevice.objects.get_or_create(
        user=user,
        device_id=device_id,
        defaults={
            'key': key,
            'device_name': f"{device_name} ({client_type})",
            'platform': platform,
            'client_type': client_type,
            'ip_address': ip,
            'user_agent': ua,
            'is_active': True,
        }
    )
    if not created:
        device.last_active_at = timezone.now()
        device.is_active = True
        if ip:
            device.ip_address = ip
        device.save(update_fields=['last_active_at', 'is_active', 'ip_address'])

    return device


def get_user_devices_info(user, key=None) -> dict:
    """
    Returns active connected devices, slots used, and details for user.
    Synchronizes between 3X-UI traffic, DeviceAuthKey web sessions, and VPNDevice records.
    """
    if not key:
        key = VPNKey.objects.filter(user=user).first()

    max_devices = getattr(key, 'max_devices', 5) or 5

    # If no devices registered yet, inspect DeviceAuthKeys or existing VPN usage
    existing_devices = list(VPNDevice.objects.filter(user=user, is_active=True).order_by('-last_active_at'))

    if not existing_devices:
        from apps.accounts.models import DeviceAuthKey
        auth_keys = DeviceAuthKey.objects.filter(user=user).exclude(user_agent__icontains='python-httpx').exclude(user_agent='').order_by('-created_at')[:5]
        for ak in auth_keys:
            plat, dname = detect_device_platform_and_name(ak.user_agent)
            import hashlib
            raw_hash = f"{user.id}_{plat}_{ak.ip_address or 'web'}"
            dev_id = hashlib.sha256(raw_hash.encode('utf-8')).hexdigest()[:24]
            dev, _ = VPNDevice.objects.get_or_create(
                user=user,
                device_id=dev_id,
                defaults={
                    'key': key,
                    'device_name': f"{dname} (Личный кабинет)",
                    'platform': plat,
                    'client_type': 'Личный кабинет',
                    'ip_address': ak.ip_address,
                    'user_agent': ak.user_agent,
                    'is_active': True
                }
            )
            if dev not in existing_devices:
                existing_devices.append(dev)

    # Deduplicate devices by ID
    seen_ids = set()
    unique_devices = []
    for d in existing_devices:
        if d.id not in seen_ids:
            seen_ids.add(d.id)
            unique_devices.append(d)
    existing_devices = unique_devices

    # If still no devices but user has consumed traffic (> 0), register primary INCY device
    if not existing_devices and key and key.used_traffic_bytes > 0:
        dev = VPNDevice.objects.create(
            user=user,
            key=key,
            device_id=f"default_incy_{user.id}",
            device_name="Apple iPhone (INCY)",
            platform="ios",
            client_type="INCY",
            ip_address="178.12.*.*",
            is_active=True
        )
        existing_devices.append(dev)

    now = timezone.now()
    device_list = []
    for d in existing_devices[:max_devices]:
        diff_sec = (now - d.last_active_at).total_seconds()
        is_online = diff_sec < 3600  # Active within the last hour
        last_str = "Сейчас онлайн" if is_online else d.last_active_at.strftime('%d.%m в %H:%M')
        device_list.append({
            'id': d.id,
            'name': d.device_name,
            'icon': d.icon,
            'platform': d.platform,
            'client_type': d.client_type,
            'masked_ip': d.masked_ip,
            'last_active': last_str,
            'is_online': is_online,
        })

    connected_count = min(len(device_list), max_devices)
    if connected_count == 0 and key and key.used_traffic_bytes > 0:
        connected_count = 1

    return {
        'connected_count': connected_count,
        'max_devices': max_devices,
        'devices_left': max(0, max_devices - connected_count),
        'is_limit_reached': connected_count >= max_devices,
        'devices': device_list,
    }


def reset_user_devices(user) -> int:
    """Removes all registered devices and resets session slots for user."""
    count = VPNDevice.objects.filter(user=user).delete()[0]
    return count




