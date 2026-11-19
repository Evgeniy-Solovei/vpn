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
from .models import VPNServer, VPNKey, VPNDevice, UserConnectionLog

logger = logging.getLogger(__name__)

# List of domains for direct routing in Russia/Belarus
DIRECT_DOMAINS = [
    # Top Level Domains
    "*.ru", "*.рф", "*.su", "*.by", "*.kz", "*.gov.kz", "*.com.kz", "*.org.kz",
    # Government & Municipal
    "gosuslugi.ru", "*.gosuslugi.ru", "gu-st.ru", "*.gu-st.ru", "nalog.ru", "*.nalog.ru",
    "lknpd.nalog.ru", "api-npd.nalog.ru", "npd.nalog.ru", "statusnpd.nalog.ru", "gnivc.ru", "*.gnivc.ru", "tax.gov.ru",
    "*.ngenix.net", "*.cdn.ngenix.net", "ngenix.ru", "*.ngenix.ru",
    "mos.ru", "*.mos.ru", "pbr.ru", "cbr.ru",
    # Bitrix24 Ecosystem
    "bitrix24.ru", "*.bitrix24.ru", "bitrix24.by", "*.bitrix24.by", "bitrix24.kz", "*.bitrix24.kz",
    "bitrix24.com", "*.bitrix24.com", "bitrix24.net", "*.bitrix24.net", "bitrix24.site", "*.bitrix24.site",
    "bitrix24.team", "*.bitrix24.team", "bitrix24kz.works", "*.bitrix24kz.works",
    "b24.ru", "*.b24.ru", "b24.by", "*.b24.by", "b24.kz", "*.b24.kz", "1c-bitrix.ru", "*.1c-bitrix.ru", "1c.ru", "*.1c.ru",
    "bitrix.info", "*.bitrix.info", "bitrix.cloud", "*.bitrix.cloud", "bx.vc", "*.bx.vc",
    "push.bitrix24.com", "pull.bitrix24.com", "rtc.bitrix24.com", "mobile.bitrix24.com",
    "b24-0jdw8s.bitrix24.kz", "*.b24-0jdw8s.bitrix24.kz",
    "kaifusushi.bitrix24.kz", "*.kaifusushi.bitrix24.kz",
    # Russian Banks & Payments
    "sberbank.ru", "*.sberbank.ru", "sber.ru", "*.sber.ru",
    "tbank.ru", "*.tbank.ru", "tinkoff.ru", "*.tinkoff.ru",
    "vtb.ru", "*.vtb.ru", "alfabank.ru", "*.alfabank.ru",
    "gazprombank.ru", "*.gazprombank.ru", "raiffeisen.ru", "*.raiffeisen.ru",
    "mir-connect.ru", "nspk.ru", "*.nspk.ru", "sbp.nspk.ru",
    # Ecosystems & Search
    "yandex.ru", "*.yandex.ru", "ya.ru", "*.ya.ru", "yastatic.net",
    "mail.ru", "*.mail.ru", "ok.ru", "*.ok.ru", "dzen.ru", "*.dzen.ru",
    # VK Ecosystem (Full bypass for VK app, video, music and CDNs)
    "vk.com", "*.vk.com", "vkvideo.ru", "*.vkvideo.ru", "userapi.com", "*.userapi.com",
    "vk-portal.net", "*.vk-portal.net", "vkuser.net", "*.vkuser.net", "vk-cdn.net", "*.vk-cdn.net",
    "vkcache.com", "*.vkcache.com", "vk.me", "*.vk.me", "vk.cc", "*.vk.cc",
    "vkplay.ru", "*.vkplay.ru", "m.vk.com", "api.vk.com",
    # E-commerce & Marketplaces (Wildberries, Ozon, Avito)
    "ozon.ru", "*.ozon.ru", "ozonusercontent.com", "*.ozonusercontent.com",
    "wildberries.ru", "*.wildberries.ru", "wb.ru", "*.wb.ru", "wbstatic.net", "*.wbstatic.net",
    "avito.ru", "*.avito.ru", "market.yandex.ru", "hh.ru", "*.hh.ru",
    # Belarusian Banks
    "belarusbank.by", "*.belarusbank.by", "priorbank.by", "*.priorbank.by",
    "alfa-bank.by", "*.alfa-bank.by", "mtbank.by", "*.mtbank.by",
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
            reality_sni=getattr(settings, 'XRAY_SNI', 'gateway.icloud.com') or 'gateway.icloud.com',
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
        self.client = httpx.Client(timeout=httpx.Timeout(2.5, connect=1.0), verify=False, follow_redirects=True)
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

    def add_or_update_client(self, key: VPNKey, reload_xray: bool = True) -> bool:
        """
        Adds or updates client in 3X-UI inbound with dynamic expiryTime.
        If user has NO active subscription or key is inactive, purges client from 3X-UI!
        """
        if not key or not key.user or not key.user.has_active_subscription or not key.is_active:
            self.delete_client(key, reload_xray=reload_xray)
            return False

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

        # Calculate exact expiration timestamp in ms based on user balance
        expiry_ms = 0
        if key.user.daily_deduction > 0 and key.user.balance > 0:
            days_remaining = float(key.user.balance / key.user.daily_deduction)
            expiry_dt = timezone.now() + timezone.timedelta(days=days_remaining)
            expiry_ms = int(expiry_dt.timestamp() * 1000)

        email = f"{key.user.username}_{key.user.id}"
        client_settings = {
            "id": str(key.key_uuid),
            "flow": "xtls-rprx-vision",
            "email": email,
            "limitIp": getattr(key, 'max_devices', 5) or 5,
            "totalGB": 0,
            "expiryTime": expiry_ms,
            "enable": True,
            "tgId": tg_id,
            "subId": key.sub_token
        }

        # 1. Try modern 3X-UI update endpoint first if client already exists.
        # Dynamic update in 3X-UI does NOT require restarting Xray (preserves active connections).
        try:
            resp = self.client.post(f"{self.base_url}/panel/api/clients/update/{email}", json=client_settings, cookies=self.cookies, headers=headers)
            if resp.status_code == 200 and resp.json().get('success'):
                logger.info(f"Successfully updated client {email} in 3X-UI with new expiry")
                return True
        except Exception as e:
            logger.debug(f"Modern 3X-UI clients/update failed: {e}")

        # 2. Try modern 3X-UI add endpoint for new clients
        modern_payload = {
            "client": client_settings,
            "inboundIds": [self.server.panel_inbound_id]
        }
        try:
            resp = self.client.post(f"{self.base_url}/panel/api/clients/add", json=modern_payload, cookies=self.cookies, headers=headers)
            if resp.status_code == 200 and resp.json().get('success'):
                logger.info(f"Successfully added client {key.user.username} to 3X-UI")
                if reload_xray:
                    self.restart_xray()
                return True
        except Exception as e:
            logger.debug(f"Modern 3X-UI clients/add failed, attempting refresh: {e}")

        # 3. Fallback to delete and re-add to ensure fresh expiryTime and enable: True
        try:
            self.delete_client(key, reload_xray=False)
            resp = self.client.post(f"{self.base_url}/panel/api/clients/add", json=modern_payload, cookies=self.cookies, headers=headers)
            if resp.status_code == 200 and resp.json().get('success'):
                logger.info(f"Successfully refreshed client {email} in 3X-UI with new expiry")
                if reload_xray:
                    self.restart_xray()
                return True
        except Exception as e:
            logger.debug(f"Re-add client failed: {e}")

        # 4. Fallback to legacy inbounds/addClient
        legacy_payload = {
            "id": self.server.panel_inbound_id,
            "settings": json.dumps({"clients": [client_settings]})
        }
        try:
            resp = self.client.post(f"{self.base_url}/panel/api/inbounds/addClient", json=legacy_payload, cookies=self.cookies, headers=headers)
            if resp.status_code == 200 and resp.json().get('success'):
                logger.info(f"Successfully added client {key.user.username} to 3X-UI (legacy API)")
                if reload_xray:
                    self.restart_xray()
                return True
            logger.warning(f"3X-UI addClient response: {resp.text}")
            return False
        except Exception as e:
            logger.error(f"Error calling addClient on 3X-UI: {e}")
            return False

    def restart_xray(self) -> bool:
        """Triggers 3X-UI to regenerate config.json and reload active Xray process."""
        if not self.login():
            return False
        headers = {}
        if self.csrf_token:
            headers['X-Csrf-Token'] = self.csrf_token
        try:
            resp = self.client.post(f"{self.base_url}/panel/api/server/restartXrayService", cookies=self.cookies, headers=headers)
            return resp.status_code == 200 and resp.json().get('success', False)
        except Exception as e:
            logger.debug(f"Restart Xray failed: {e}")
            return False

    def add_client(self, key: VPNKey, reload_xray: bool = True) -> bool:
        return self.add_or_update_client(key, reload_xray=reload_xray)

    def delete_client(self, key: VPNKey, reload_xray: bool = True) -> bool:
        if not self.login():
            return True
        headers = {}
        if self.csrf_token:
            headers['X-Csrf-Token'] = self.csrf_token

        email = f"{key.user.username}_{key.user.id}"
        success = False
        # 1. Try modern 3X-UI API
        try:
            resp = self.client.post(f"{self.base_url}/panel/api/clients/del/{email}", cookies=self.cookies, headers=headers)
            if resp.status_code == 200 and resp.json().get('success'):
                logger.info(f"Successfully deleted client {email} from 3X-UI")
                success = True
        except Exception:
            pass

        # 2. Fallback to legacy
        if not success:
            del_url = f"{self.base_url}/panel/api/inbounds/{self.server.panel_inbound_id}/delClient/{key.key_uuid}"
            try:
                resp = self.client.post(del_url, cookies=self.cookies, headers=headers)
                success = resp.status_code == 200
            except Exception as e:
                logger.error(f"Error deleting client on 3X-UI: {e}")
                success = False

        if success and reload_xray:
            self.restart_xray()
        return success


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


def get_incy_routing_dict(key=None) -> dict:
    """
    Generates dynamic routing JSON profile for INCY application.
    Uses reliable UDP DNS (8.8.8.8 and 8.8.4.4) to eliminate DoH handshake failures and timeouts.
    When whitelist_enabled=True: routes VK, banks, Gosuslugi, domestic media & marketplaces
    directly (bypassing VPN to eliminate 'VPN detected' banners), while proxying blocked sites.
    When whitelist_enabled=False: routes all traffic through the active VPN node.
    """
    whitelist_enabled = getattr(key, 'whitelist_enabled', True) if key else True

    if whitelist_enabled:
        direct_sites = [
            "domain:local",
            "domain:localhost",
        ]

        # Active direct zones configured for this key (default: ru, by, kz, su, рф)
        active_zones = key.get_direct_zones() if (key and hasattr(key, 'get_direct_zones')) else ['ru', 'by', 'kz', 'su', 'рф', 'xn--p1ai']
        for z in active_zones:
            if z in ('ru',):
                direct_sites.extend([
                    "regexp:.*\\.ru$",
                    "domain:ru", "domain:com.ru", "domain:net.ru", "domain:org.ru", "domain:msk.ru", "domain:spb.ru"
                ])
            elif z in ('by',):
                direct_sites.extend([
                    "regexp:.*\\.by$",
                    "domain:by", "domain:gov.by", "domain:mil.by"
                ])
            elif z in ('kz',):
                direct_sites.extend([
                    "regexp:.*\\.kz$",
                    "domain:kz", "domain:com.kz", "domain:org.kz", "domain:gov.kz"
                ])
            elif z in ('su',):
                direct_sites.extend(["regexp:.*\\.su$", "domain:su"])
            elif z in ('рф', 'xn--p1ai'):
                if "regexp:.*\\.xn--p1ai$" not in direct_sites:
                    direct_sites.extend(["regexp:.*\\.xn--p1ai$", "domain:xn--p1ai"])
            else:
                direct_sites.extend([f"regexp:.*\\.{z}$", f"domain:{z}"])

        # Core Russian & Belarusian government and service ecosystem (always direct when whitelist_enabled)
        direct_sites.extend([
            "domain:gov.ru",
            "domain:kremlin.ru",
            "domain:duma.gov.ru",
            "domain:council.gov.ru",
            # Explicit VK Ecosystem (prevents 'VPN detected' banner in VK app/web)
            "domain:vk.com",
            "domain:vk.ru",
            "domain:vk.me",
            "domain:vk.cc",
            "domain:vk.link",
            "domain:userapi.com",
            "domain:vk-cdn.net",
            "domain:vkuseraudio.net",
            "domain:vkuser.net",
            "domain:vk-portal.net",
            "domain:vkcache.com",
            "domain:vkplay.ru",
            "domain:vkvideo.ru",
            "domain:m.vk.com",
            "domain:api.vk.com",
            "domain:oauth.vk.com",
            "domain:login.vk.com",
            "domain:id.vk.com",
            "domain:connect.vk.com",
            "domain:vkforms.ru",
            "domain:vklive.net",
            "domain:vkclips.ru",
            "domain:vk-apps.com",
            "domain:vkcalls.ru",
            "domain:vkontakte.ru",
            "domain:vk.company",
            "domain:vkgo.ru",
            "domain:vkusercdn.net",
            "domain:vkuserlive.net",
            "domain:vkuserphoto.net",
            "domain:vkuservideo.net",
            "domain:vk-analytics.com",
            # Mail.ru Ecosystem (Mail app, Cloud, Auth, Imap/Smtp)
            "domain:mail.ru",
            "domain:e.mail.ru",
            "domain:inbox.ru",
            "domain:bk.ru",
            "domain:list.ru",
            "domain:imgsmail.ru",
            "domain:cloud.mail.ru",
            "domain:m.mail.ru",
            "domain:api.mail.ru",
            "domain:auth.mail.ru",
            "domain:filin.mail.ru",
            "domain:octavius.mail.ru",
            "domain:target.my.com",
            "domain:my.games",
            "domain:mycdn.me",
            "domain:touch.mail.ru",
            "domain:ok.ru",
            "domain:odnoklassniki.ru",
            "domain:tam-tam.me",
            # Bitrix24 Ecosystem (Bitrix24 cloud portals, CRM, mobile app, OAuth, Push, Pull)
            "regexp:.*\\.bitrix24\\..*$",
            "regexp:.*\\.b24\\..*$",
            "regexp:.*\\.bitrix\\..*$",
            "regexp:.*\\.1c-bitrix\\..*$",
            "regexp:.*\\.bitrix24kz\\.works$",
            "regexp:.*\\.bitrix24site\\.ru$",
            "regexp:.*\\.bitrix24\\.team$",
            "regexp:.*\\.bx\\.vc$",
            "domain:bitrix24.ru",
            "domain:bitrix24.by",
            "domain:bitrix24.com",
            "domain:bitrix24.kz",
            "domain:bitrix24.net",
            "domain:bitrix24.team",
            "domain:bitrix24kz.works",
            "domain:auth2.bitrix24.net",
            "domain:bitrix24.eu",
            "domain:bitrix24.site",
            "domain:bitrix24.tech",
            "domain:bitrix24.link",
            "domain:bitrix24.de",
            "domain:bitrix24.in",
            "domain:bitrix24.pl",
            "domain:bitrix24.to",
            "domain:bitrix.com",
            "domain:bitrix.ru",
            "domain:bitrix.kz",
            "domain:bitrix.info",
            "domain:bitrix.cloud",
            "domain:bitrix-cloud.com",
            "domain:bitrix-cloud.ru",
            "domain:bitrix-cloud.net",
            "domain:1c-bitrix.ru",
            "domain:1c-bitrix.by",
            "domain:1c-bitrix.kz",
            "domain:1c.ru",
            "domain:b24.by",
            "domain:b24.ru",
            "domain:b24.kz",
            "domain:b24.to",
            "domain:b24-am.com",
            "domain:b24.site",
            "domain:b24.help",
            "domain:b24.market",
            "domain:b24.top",
            "domain:b24.network",
            "domain:bitrix24.network",
            "domain:bx.vc",
            # Bitrix OAuth & Auth (critical — mobile app authenticates here, NOT on .ru/.kz TLD!)
            "domain:oauth.bitrix.info",
            "domain:www.bitrix.info",
            "domain:cp.bitrix.info",
            # Bitrix24 Global CDN, IM, Push-Server (AWS US/CloudFront — not in geoip:ru!)
            "domain:im-web.bitrix24.com",
            "domain:push-server.bitrix24.com",
            "domain:cdn.bitrix24.com",
            "domain:dl.bitrix24.com",
            "domain:dl.bitrix24.ru",
            "domain:cdn.bitrix24.ru",
            # Kazakhstan top-level domain & cloud
            "domain:kz",
            "domain:com.kz",
            "domain:org.kz",
            # Anti-DDoS & Protection Proxies used by Russian services (Bitrix, Banks)
            "domain:qrator.net",
            "domain:qrator.com",
            "domain:ddos-guard.net",
            "domain:ddosguard.net",
            "domain:stormwall.pro",
            "domain:stormwall.network",
            "domain:stormwall.ru",
            "domain:live-dev.by",
            # Sberbank Ecosystem (Online app, API, ID, Kuper/SberMarket)
            "domain:sberbank.ru",
            "domain:sberbank.com",
            "domain:sber.ru",
            "domain:sberid.ru",
            "domain:sberprime.ru",
            "domain:spasibosberbank.ru",
            "domain:sberauto.com",
            "domain:sbermegamarket.ru",
            "domain:megamarket.ru",
            "domain:sbermarket.ru",
            "domain:kuper.ru",
            "domain:sberbank-tele.com",
            "domain:sberleasing.ru",
            "domain:sberinvest.ru",
            "domain:domclick.ru",
            # Russian Government & Public Services
            "domain:gosuslugi.ru",
            "domain:gosuslugi.by",
            "domain:gu-st.ru",
            "domain:esia.gosuslugi.ru",
            "domain:epgu.gosuslugi.ru",
            "domain:partners.gosuslugi.ru",
            "domain:pos.gosuslugi.ru",
            "domain:gosuslugi-online.ru",
            "domain:gosuslugi-cdn.ru",
            "domain:smev.gosuslugi.ru",
            "domain:pgu.mos.ru",
            "domain:nalog.ru",
            "domain:nalog.gov.ru",
            "domain:lknpd.nalog.ru",
            "domain:api-npd.nalog.ru",
            "domain:npd.nalog.ru",
            "domain:statusnpd.nalog.ru",
            "domain:npd-app.nalog.ru",
            "domain:auth-npd.nalog.ru",
            "domain:lkfl.nalog.ru",
            "domain:lkfl2.nalog.ru",
            "domain:lkul.nalog.ru",
            "domain:lkip.nalog.ru",
            "domain:gnivc.ru",
            "domain:tax.gov.ru",
            # FNS additional infrastructure (mobile app auth, session, CNAME targets)
            "domain:lknpd.gi.nalog.ru",
            "domain:fns.ru",
            "domain:data.nalog.ru",
            "domain:service.nalog.ru",
            "domain:old.nalog.ru",
            "domain:login.nalog.ru",
            "domain:cabinet.nalog.ru",
            # NGENIX CDN & state CDN infrastructure (powers npd.nalog.ru and FNS static assets)
            "domain:ngenix.net",
            "domain:cdn.ngenix.net",
            "domain:ngenix.ru",
            "domain:cdnvideo.ru",
            "domain:cdnvideo.net",
            "regexp:.*\\.ngenix\\.net$",
            "regexp:.*\\.ngenix\\.ru$",
            "regexp:.*\\.cdnvideo\\.ru$",
            "regexp:.*\\.cdnvideo\\.net$",
            # Bitrix24 Global Push & Kazakh cloud
            "domain:push.bitrix24.com",
            "domain:push.bitrix24.ru",
            "domain:push.bitrix24.kz",
            "domain:pull.bitrix24.com",
            "domain:pull.bitrix24.ru",
            "domain:pull.bitrix24.kz",
            "domain:rtc.bitrix24.com",
            "domain:mobile.bitrix24.com",
            "domain:mobile.bitrix24.ru",
            "domain:mobile.bitrix24.kz",
            "domain:cloud-push.bitrix24.com",
            "domain:b24-0jdw8s.bitrix24.kz",
            "full:b24-0jdw8s.bitrix24.kz",
            "domain:kaifusushi.bitrix24.kz",
            "domain:mos.ru",
            "domain:sfr.gov.ru",
            "domain:fss.ru",
            "domain:pfr.gov.ru",
            "domain:pbr.ru",
            "domain:cbr.ru",
            "domain:customs.gov.ru",
            "domain:fssp.gov.ru",
            "domain:mvd.ru",
            "domain:digital.gov.ru",
            # Banks & Payment Systems (RU & BY)
            "domain:tbank.ru",
            "domain:tinkoff.ru",
            "domain:tcsbank.ru",
            "domain:alfabank.ru",
            "domain:alfa-bank.by",
            "domain:alfabank.by",
            "domain:vtb.ru",
            "domain:vtb.by",
            "domain:gazprombank.ru",
            "domain:raiffeisen.ru",
            "domain:mir-connect.ru",
            "domain:nspk.ru",
            "domain:sbp.nspk.ru",
            "domain:belarusbank.by",
            "domain:priorbank.by",
            "domain:mtbank.by",
            "domain:belinvestbank.by",
            "domain:statusbank.by",
            "domain:bsb.by",
            "domain:bnb.by",
            # Ecosystems, Search & Media
            "domain:yandex.ru",
            "domain:yandex.by",
            "domain:yandex.net",
            "domain:yandex.com",
            "domain:appmetrica.yandex.net",
            "domain:mobile.yandex.net",
            "domain:csa.yandex.net",
            "domain:ya.ru",
            "domain:yastatic.net",
            "domain:dzen.ru",
            "domain:ok.ru",
            # Marketplaces & Logistics
            "domain:avito.ru",
            "domain:wildberries.ru",
            "domain:wb.ru",
            "domain:wbstatic.net",
            "domain:ozon.ru",
            "domain:ozonusercontent.com",
            "domain:cdek.ru",
            "domain:pochta.ru",
            # Streaming & Media (RF)
            "domain:kinopoisk.ru",
            "domain:ivi.ru",
            "domain:okko.tv",
            "domain:rutube.ru",
            "domain:smotrim.ru",
            "domain:premier.one",
            "domain:kion.ru",
            "domain:more.tv",
        ])
        # Dedicated domestic IP CIDR blocks (AS47541, AS34700, AS197695, AS47764, AS13238, etc.)
        # Direct routing guarantees raw socket connections bypass the VPN tunnel
        direct_ips = [
            # Standard private RFC1918 subnets (guarantees local LAN never enters VPN)
            "geoip:private",
            "10.0.0.0/8",
            "172.16.0.0/12",
            "192.168.0.0/16",
            "127.0.0.0/8",
            "169.254.0.0/16",
            "::1/128",
            "fc00::/7",
            "fe80::/10",
            # GeoIP rules: route entire Russian, Belarusian and Kazakh IP space DIRECT
            "geoip:ru",
            "geoip:by",
            "geoip:kz",
            # Rostelecom / FNS / Gosuslugi / NGENIX CDN & GNIVC subnets
            "213.24.0.0/16",
            "213.59.0.0/16",
            "195.208.0.0/16",
            "195.209.0.0/16",
            "178.208.0.0/16",
            "212.193.144.0/20",
            "46.235.184.0/21",
            "37.220.160.0/21",
            "78.41.104.0/21",
            "80.85.240.0/20",
            "185.17.168.0/22",
            "109.207.0.0/16",
            "93.93.88.0/21",
            "95.173.136.0/21",
            "195.82.128.0/19",
            "212.164.0.0/16",
            "62.76.0.0/16",
            "80.82.0.0/16",
            "188.254.0.0/16",
            "217.107.0.0/16",
            "94.25.0.0/16",
            "178.62.192.0/18",
            # VK (AS47541 & edge nodes)
            "87.240.128.0/18",
            "93.186.224.0/20",
            "95.142.192.0/20",
            "95.213.0.0/17",
            "185.32.248.0/22",
            "185.131.68.0/23",
            "79.137.128.0/17",
            "5.181.61.0/24",
            "89.221.235.0/24",
            "91.231.132.0/22",
            "217.69.128.0/20",
            "217.69.132.0/22",
            "217.69.136.0/21",
            # Sberbank (AS34700 & AS197695)
            "194.54.14.0/23",
            "194.54.12.0/24",
            "193.243.144.0/22",
            "84.252.128.0/19",
            "91.223.180.0/22",
            "185.150.152.0/22",
            "195.239.210.0/24",
            "194.186.207.0/24",
            "212.45.1.0/24",
            # Mail.ru (AS47764)
            "94.100.176.0/20",
            "94.100.180.0/22",
            "217.69.139.0/24",
            "128.140.168.0/21",
            # Yandex (AS13238)
            "87.250.224.0/19",
            "93.158.128.0/18",
            "213.180.192.0/19",
            "5.255.255.0/24",
            "77.88.8.0/24",
            "77.88.0.0/18",
            # T-Bank (AS41994)
            "91.194.226.0/23",
            "185.148.80.0/22",
            # Alfa-Bank (AS15944)
            "217.12.96.0/20",
            # Qrator / Anti-DDoS / Bitrix Cloud clusters (AS51115, AS209671)
            "178.248.224.0/19",
            "185.104.208.0/21",
            "46.174.140.0/21",
            "81.161.98.0/23",
            "132.243.176.0/22",
            "78.155.198.0/24",
            # VK Cloud / Bitrix Hosting (AS47764)
            "217.16.16.0/20",
            # Kazakhstan Bitrix Cloud & VK Cloud KZ (AS48716, AS201817)
            "89.35.125.0/24",
            "195.49.210.0/23",
            "194.31.156.0/22",
            "194.31.159.0/24",
            "185.22.64.0/22",
            "91.201.214.0/23",
            "185.137.235.0/24",
            "185.146.2.0/24",
            # FNS / GNIVC (AS28682)
            "185.49.0.0/22",
            "145.14.48.0/21",
            "193.243.140.0/23",
            "145.14.8.0/21",
            # NGENIX CDN full IPv4 coverage (AS34879)
            "195.208.64.0/19",
            "195.209.64.0/18",
            # AWS subnets hosting Bitrix24 global services (push, pull, mobile, cdn, oauth)
            # 54.83.26.42 — push/pull/mobile/rtc/cdn.bitrix24.com
            "54.83.26.0/24",
            # 18.201.1.1 — oauth.bitrix.info (AWS eu-west-1 Ireland)
            "18.201.0.0/16",
            # CloudFront CDN for dl.bitrix24.com (99.86.x.x, 13.x.x.x)
            "99.86.0.0/16",
            "99.84.0.0/16",
        ]
        route_order = "block-direct-proxy"
        profile_name = "VPN live-dev Умный обход (ВК, Банки, Битрикс, Почта)"
        global_proxy = True
    else:
        direct_sites = ["domain:local", "domain:localhost"]
        direct_ips = [
            "10.0.0.0/8",
            "172.16.0.0/12",
            "192.168.0.0/16",
            "127.0.0.0/8",
            "169.254.0.0/16",
        ]
        route_order = "block-direct-proxy"
        profile_name = "VPN live-dev (Весь трафик)"
        global_proxy = True

    if key:
        for d in key.get_custom_domains():
            clean = d.strip().lower()
            if clean and f"domain:{clean}" not in direct_sites:
                direct_sites.append(f"domain:{clean}")

    proxy_sites = [
        "domain:youtube.com",
        "domain:youtu.be",
        "domain:googlevideo.com",
        "domain:ytimg.com",
        "domain:ggpht.com",
        "domain:telegram.org",
        "domain:t.me",
        "domain:telegram.me",
        "domain:telesco.pe",
        "domain:google.com",
        "domain:play.google.com",
        "domain:googleusercontent.com",
        "domain:android.com",
        "domain:github.com",
        "domain:githubassets.com",
        "domain:githubusercontent.com",
        "domain:instagram.com",
        "domain:cdninstagram.com",
        "domain:threads.net",
        "domain:twitter.com",
        "domain:x.com",
        "domain:t.co",
        "domain:twimg.com",
        "domain:openai.com",
        "domain:chatgpt.com",
        "domain:oaistatic.com",
        "domain:oaiusercontent.com",
        "domain:anthropic.com",
        "domain:claude.ai",
        "domain:perplexity.ai",
        "domain:facebook.com",
        "domain:fb.com",
        "domain:fbcdn.net",
        "domain:meta.com",
        "domain:discord.com",
        "domain:discord.gg",
        "domain:discordapp.com",
        "domain:discordapp.net",
        "domain:notion.so",
        "domain:spotify.com",
        "domain:medium.com",
        "domain:canva.com",
        "domain:flaticon.com",
        "domain:freepik.com",
        "domain:rutracker.org",
        "domain:nnmclub.to",
        "domain:rutor.info",
        "domain:kinozal.tv",
        "domain:hdrezka.ag",
        "domain:rezka.ag",
        "domain:filmix.ac",
        "domain:flibusta.is",
        "domain:flibusta.bwh.zone",
        "domain:meduza.io",
        "domain:bbc.com",
        "domain:dw.com",
        "domain:svoboda.org",
        "domain:zona.media",
        "domain:theins.ru",
        "domain:holod.media",
        "domain:novayagazeta.eu",
        "domain:patreon.com",
        "domain:linkedin.com",
        "domain:licdn.com",
        "domain:proton.me",
        "domain:protonmail.com",
        "domain:protonvpn.com",
        "domain:midjourney.com",
        "domain:ai.com",
    ]
    if key and hasattr(key, 'get_custom_proxy_domains'):
        for d in key.get_custom_proxy_domains():
            clean = d.strip().lower()
            if clean and f"domain:{clean}" not in proxy_sites:
                proxy_sites.insert(0, f"domain:{clean}")

    result = {
        "Name": profile_name,
        "GlobalProxy": global_proxy,
        "RouteOrder": route_order,
        "RemoteDNSType": "DoU",
        "RemoteDNSDomain": "",
        "RemoteDNSIP": "8.8.8.8",
        "RemoteDns": "8.8.8.8",
        "DomesticDNSType": "DoU",
        "DomesticDNSDomain": "",
        "DomesticDNSIP": "77.88.8.8",
        "DomesticDns": "77.88.8.8",
        "Geoipurl": "https://github.com/Loyalsoldier/v2ray-rules-dat/releases/latest/download/geoip.dat",
        "Geositeurl": "https://github.com/Loyalsoldier/v2ray-rules-dat/releases/latest/download/geosite.dat",
        "LastUpdated": str(int(time.time())),
        "DnsHosts": {
            # Force oauth.bitrix.info to Qrator/1C-Bitrix Russia (not AWS Ireland 18.201.1.1)
            # Google DNS returns Ireland IP; Yandex DNS returns correct Russian IP 178.248.237.41
            "oauth.bitrix.info": "178.248.237.41"
        },
        "DirectSites": direct_sites,
        "DirectIp": direct_ips,
        "ProxySites": proxy_sites,
        "ProxyIp": [
            # Meta / Instagram / Facebook
            "31.13.24.0/21", "31.13.64.0/18", "45.64.40.0/22", "66.220.144.0/20",
            "69.63.176.0/20", "69.171.224.0/19", "74.119.76.0/22", "103.4.96.0/22",
            "129.134.0.0/16", "157.240.0.0/16", "173.252.64.0/18", "179.60.192.0/22",
            "185.60.216.0/22", "204.15.20.0/22",
            # Twitter / X
            "104.244.42.0/21", "192.133.76.0/22", "199.16.156.0/22", "199.59.148.0/22",
            "199.96.56.0/21", "209.237.192.0/19",
            # Discord Voice
            "66.22.196.0/22", "66.22.200.0/22", "66.22.204.0/22", "66.22.208.0/20",
            # YouTube / Google Video
            "142.250.0.0/15", "172.217.0.0/16", "216.58.192.0/19", "74.125.0.0/16",
            "173.194.0.0/16", "209.85.128.0/17", "64.233.160.0/19", "66.102.0.0/20",
            "66.249.64.0/19", "108.177.0.0/17"
        ],
        "BlockSites": [],
        "BlockIp": [],
        "DomainStrategy": "IPIfNonMatch",
        "FakeDNS": False,
        "UseChunkFiles": False
    }

    return result


def check_server_health_from_russia(ip: str, port: int, timeout: float = 4.0) -> dict:
    """
    Checks TCP port connectivity to server from inside Russia (Moscow monitoring node).
    Detects TSPU / RKN blocking by verifying handshake from Russian AS210644 node.
    """
    try:
        url = f"https://check-host.net/check-tcp?host={ip}:{port}&node=ru2.node.check-host.net"
        headers = {'Accept': 'application/json', 'User-Agent': 'VPNLiveDevMonitor/1.0'}
        with httpx.Client(timeout=timeout, verify=False) as client:
            resp = client.get(url, headers=headers)
            if resp.status_code != 200:
                return {'success': None, 'error': f"check-host status {resp.status_code}"}
            data = resp.json()
            req_id = data.get('request_id')
            if not req_id:
                return {'success': None, 'error': 'no_request_id'}

            time.sleep(2.5)
            res_url = f"https://check-host.net/check-result/{req_id}"
            res_resp = client.get(res_url, headers=headers)
            if res_resp.status_code != 200:
                return {'success': None, 'error': f"check-host result status {res_resp.status_code}"}
            res_data = res_resp.json()
            node_res = res_data.get('ru2.node.check-host.net')
            if node_res and isinstance(node_res, list) and len(node_res) > 0 and node_res[0]:
                first = node_res[0]
                if isinstance(first, dict):
                    if 'time' in first:
                        ping_ms = max(5, int(first['time'] * 1000))
                        return {'success': True, 'status': 'online', 'ping_ms': ping_ms}
                    elif 'error' in first:
                        return {'success': False, 'status': 'blocked_rkn', 'error': first['error']}
            return {'success': None, 'error': 'no node data returned'}
    except Exception as e:
        return {'success': None, 'error': str(e)}


def check_server_health(server: VPNServer, timeout: float = 2.5) -> dict:
    """
    Measures latency to VPNServer and detects network drops / RKN blocking from inside Russia.
    """
    from django.utils import timezone

    # 1. First attempt: Real check from inside Russia (Moscow node)
    russia_check = check_server_health_from_russia(server.ip, server.port)
    if russia_check.get('success') is True:
        ping_ms = russia_check['ping_ms']
        server.mark_online(ping=ping_ms)
        logger.info(f"Server {server.clean_name} ({server.ip}:{server.port}) verified ONLINE from Moscow, ping: {ping_ms}ms")
        return {'success': True, 'status': 'online', 'ping_ms': ping_ms}
    elif russia_check.get('success') is False:
        err = russia_check.get('error', 'Blocked in Russia')
        server.mark_blocked_rkn(reason=f"TSPU / RKN blocked in Moscow: {err}")
        logger.warning(f"Server {server.clean_name} ({server.ip}:{server.port}) BLOCKED_RKN from Moscow: {err}")
        return {'success': False, 'status': 'blocked_rkn', 'error': err}

    # 2. Fallback: Direct TCP socket ping (if external check-host API is degraded)
    t_start = time.perf_counter()
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect((server.ip, server.port))
        sock.close()
        elapsed_ms = max(5, int((time.perf_counter() - t_start) * 1000))
        server.mark_online(ping=elapsed_ms)
        logger.info(f"Server {server.clean_name} ({server.ip}:{server.port}) is ONLINE (fallback ping: {elapsed_ms}ms)")
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

    if count > 0:
        admin_text = (
            f"🔄 <b>АВТО-СПАСЕНИЕ ПОЛЬЗОВАТЕЛЕЙ (Auto-Failover)</b>\n\n"
            f"⚠️ Сервер был помечен как заблокированный или недоступный.\n"
            f"👥 Переведено абонентов: <b>{count}</b>\n"
            f"🟢 Новый рабочий сервер: <b>{healthy_server.display_name}</b> (порт {healthy_server.port}, пинг {healthy_server.ping_ms} мс)\n"
            f"💡 Ключи абонентов уже перенаправлены на рабочий узел."
        )
        notify_admin(admin_text)

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
    """Ensures client key UUID is synced with 3X-UI inbound on the server."""
    if not key or not key.server or not key.server.panel_url:
        return False
    try:
        svc = ThreeXUIService(key.server)
        if not key.user.has_active_subscription or not key.is_active:
            svc.delete_client(key)
            return False
        return svc.add_or_update_client(key)
    except Exception as e:
        logger.debug(f"Error in ensure_key_in_panel: {e}")
        return False


def ensure_key_in_all_active_servers(key: VPNKey) -> int:
    """
    Ensures client key UUID is synced across ALL active VPN servers with panels.
    If user subscription expired or key is inactive, purges client from all panels.
    """
    if not key or not key.user:
        return 0
    synced = 0
    active_servers = VPNServer.objects.filter(is_active=True).exclude(panel_url__isnull=True).exclude(panel_url='')
    is_valid = key.user.has_active_subscription and key.is_active
    for srv in active_servers:
        try:
            svc = ThreeXUIService(srv)
            if is_valid:
                if svc.add_or_update_client(key):
                    synced += 1
            else:
                svc.delete_client(key)
        except Exception as e:
            logger.debug(f"Error syncing key on server {srv.clean_name}: {e}")
    return synced


def sync_all_keys_to_panel() -> int:
    """Ensures all active keys are registered across all active 3X-UI inbounds."""
    synced = 0
    active_servers = list(VPNServer.objects.filter(is_active=True).exclude(panel_url__isnull=True).exclude(panel_url=''))
    for key in VPNKey.objects.filter(is_active=True).select_related('server', 'user'):
        for srv in active_servers:
            try:
                svc = ThreeXUIService(srv)
                if svc.add_client(key, reload_xray=False):
                    synced += 1
            except Exception:
                pass
    return synced


def detect_device_platform_and_name(ua: str) -> tuple[Optional[str], Optional[str]]:
    """Parses User-Agent to determine platform and friendly device name."""
    ua_str = (ua or "").lower()

    # Ignore automated scripts, health-checks, curl, python
    if any(bot in ua_str for bot in ["curl", "python", "wget", "aiohttp", "urllib", "go-http-client"]):
        return None, None

    # Check Mac FIRST (macOS also uses CFNetwork and Darwin!)
    if "macintosh" in ua_str or "mac os x" in ua_str or "macos" in ua_str:
        return "macos", "Apple Mac"

    # iOS (iPhone / iPad)
    if "iphone" in ua_str:
        return "ios", "Apple iPhone"
    if "ipad" in ua_str:
        return "ios", "Apple iPad"
    if "cfnetwork" in ua_str or "darwin" in ua_str:
        return "ios", "Apple iPhone"

    # Android
    if "android" in ua_str:
        return "android", "Android Смартфон"

    # Windows
    if "windows" in ua_str:
        return "windows", "Windows Компьютер"

    # Smart TV
    if "tv" in ua_str or "tizen" in ua_str or "webos" in ua_str or "bravia" in ua_str:
        return "tv", "Smart TV"

    # Routers
    if "sing-box" in ua_str or "v2ray" in ua_str or "xray" in ua_str or "clash" in ua_str:
        return "router", "Роутер"

    return "other", "Мобильное устройство"


def register_user_device(user, request=None, key=None, client_type="INCY") -> Optional[VPNDevice]:
    """Registers or updates a VPNDevice entry for the user. Strictly 1 device per platform."""
    if not user or (not user.is_authenticated and not getattr(user, 'id', None)):
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
    if not platform:
        return None

    # Strictly deterministic per user + platform to prevent duplicates
    device_id = f"{user.id}_{platform}"

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
        device.device_name = f"{device_name} ({client_type})"
        if ip:
            device.ip_address = ip
        if ua:
            device.user_agent = ua
        device.save(update_fields=['last_active_at', 'is_active', 'device_name', 'ip_address', 'user_agent'])

    return device


def get_user_devices_info(user, key=None) -> dict:
    """
    Returns active connected devices, slots used, and details for user.
    Guarantees no duplicate devices by enforcing 1 slot per platform.
    """
    if not key:
        key = VPNKey.objects.filter(user=user).first()

    max_devices = getattr(key, 'max_devices', 5) or 5

    # Clean up any legacy phantom browser records, curl, or stale test tools
    VPNDevice.objects.filter(user=user, client_type='Личный кабинет').delete()
    VPNDevice.objects.filter(user=user, user_agent__icontains='curl').delete()
    VPNDevice.objects.filter(user=user, user_agent__icontains='python').delete()

    existing_devices = list(VPNDevice.objects.filter(user=user, is_active=True).order_by('-last_active_at'))

    # Strictly deduplicate devices by platform: 1 Mac, 1 iPhone, etc.
    seen_platforms = set()
    unique_devices = []
    for d in existing_devices:
        if d.platform not in seen_platforms:
            seen_platforms.add(d.platform)
            unique_devices.append(d)
        else:
            # Delete stale duplicate record from DB
            try:
                d.delete()
            except Exception:
                pass
    existing_devices = unique_devices

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

    return {
        'connected_count': connected_count,
        'max_devices': max_devices,
        'devices_left': max(0, max_devices - connected_count),
        'is_limit_reached': connected_count >= max_devices,
        'devices': device_list,
    }


def delete_user_device(user, device_id) -> bool:
    """Removes a specific registered device for user by PK or device_id."""
    if not user:
        return False
    query = models.Q(user=user)
    if str(device_id).isdigit():
        query &= (models.Q(id=int(device_id)) | models.Q(device_id=str(device_id)))
    else:
        query &= models.Q(device_id=str(device_id))
    
    deleted, _ = VPNDevice.objects.filter(query).delete()
    return deleted > 0


def reset_user_devices(user) -> int:
    """Removes all registered devices and resets session slots for user."""
    if not user:
        return 0
    count = VPNDevice.objects.filter(user=user).delete()[0]
    return count


def notify_admin(text: str, reply_markup: dict = None) -> bool:
    """
    Safely dispatches high-priority system and user-incident notifications
    to the administrator via Telegram Bot.
    """
    import sys
    if 'test' in sys.argv:
        return False

    from django.conf import settings
    bot_token = getattr(settings, 'BOT_TOKEN', '')
    admin_id_str = str(getattr(settings, 'ADMIN_TELEGRAM_ID', '777842796')).strip()
    if not bot_token or not admin_id_str:
        return False

    admin_ids = [aid.strip() for aid in admin_id_str.replace(';', ',').split(',') if aid.strip()]
    success = False
    for admin_id in admin_ids:
        try:
            payload = {
                "chat_id": admin_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True
            }
            if reply_markup:
                payload["reply_markup"] = reply_markup
            with httpx.Client(timeout=4.0, trust_env=False) as client:
                resp = client.post(
                    f"https://api.telegram.org/bot{bot_token}/sendMessage",
                    json=payload
                )
                if resp.status_code == 200:
                    success = True
                else:
                    logger.warning(f"Telegram admin notify failed to {admin_id}: {resp.status_code} {resp.text}")
        except Exception as e:
            logger.error(f"Error sending admin alert to {admin_id}: {e}")
    return success


def diagnose_user_vpn(user, client_ip: str = None, user_agent: str = None) -> dict:
    """
    Performs comprehensive per-user VPN connectivity diagnosis:
    1. Checks subscription expiration and balance.
    2. Inspects 3X-UI SQLite stats (up/down/last_online/last_sub_fetch).
    3. Checks server health & RKN accessibility status.
    4. Detects stale configuration vs server port/SNI changes.
    5. Detects traffic stall (packets sent, zero received).
    6. Logs event to UserConnectionLog and notifies admin via Telegram.
    """
    from django.utils import timezone
    import sqlite3
    import datetime

    key = VPNKey.objects.filter(user=user, is_active=True).first()
    if not key:
        return {
            'status': 'no_key',
            'title': 'VPN Ключ не найден',
            'message': 'У вас нет активного VPN-ключа. Перейдите в меню и создайте подключение.',
            'recommendation': 'create_key'
        }

    server = key.server
    dev = VPNDevice.objects.filter(user=user).order_by('-last_active_at').first()
    device_name = f"{dev.icon} {dev.device_name}" if dev else "Мобильное устройство"

    up = 0
    down = 0
    last_online_ms = 0
    last_sub_fetch_ms = 0

    # Query local 3X-UI SQLite if on server
    db_path = '/etc/x-ui/x-ui.db'
    if os.path.exists(db_path):
        try:
            email = f"{user.username}_{user.id}"
            conn = sqlite3.connect(db_path, timeout=3)
            cur = conn.cursor()
            cur.execute("SELECT up, down, last_online, last_sub_fetch FROM client_traffics WHERE email=?", (email,))
            row = cur.fetchone()
            conn.close()
            if row:
                up = row[0] or 0
                down = row[1] or 0
                last_online_ms = row[2] or 0
                last_sub_fetch_ms = row[3] or 0
        except Exception as e:
            logger.warning(f"Error querying 3X-UI SQLite for diagnosis: {e}")

    # Fallback to key values if local DB didn't have it
    if up == 0 and down == 0 and key.used_traffic_bytes > 0:
        up = int(key.used_traffic_bytes * 0.1)
        down = int(key.used_traffic_bytes * 0.9)

    now = timezone.now()
    now_ms = int(now.timestamp() * 1000)

    # Check last sub fetch
    hours_since_sub = 999
    if last_sub_fetch_ms > 0:
        hours_since_sub = round((now_ms - last_sub_fetch_ms) / (1000 * 3600), 1)
    elif dev and dev.last_active_at:
        hours_since_sub = round((now - dev.last_active_at).total_seconds() / 3600, 1)

    # Determine diagnosis
    status = 'healthy'
    diagnosis_title = '🟢 Соединение в норме'
    user_msg = (
        f"🟢 <b>С сервером всё в порядке!</b>\n\n"
        f"Узел <b>{server.clean_name}</b> доступен (порт {server.port}, пинг ~{server.ping_ms} мс).\n\n"
        f"💡 <b>Если сайты не открываются:</b>\n"
        f"1. Выключите и включите тумблер VPN в приложении (переподключение).\n"
        f"2. Перезапустите приложение или браузер.\n"
        f"3. Если не помогло — нажмите кнопку «Сменить сервер» ниже."
    )

    if not user.has_active_subscription:
        status = 'expired'
        diagnosis_title = '🔴 Подписка закончилась'
        user_msg = (
            f"🔴 <b>Ваша подписка или пробный период закончились</b>\n\n"
            f"Баланс: {user.balance} ₽. Пополните баланс в меню бота, чтобы доступ активировался автоматически."
        )
    elif server.health_status == 'blocked_rkn' or not server.is_active:
        status = 'server_blocked'
        diagnosis_title = '🔴 Сервер заблокирован ТСПУ'
        user_msg = (
            f"⚠️ <b>Временная блокировка узла провайдерами РФ</b>\n\n"
            f"Сервер {server.clean_name} испытывает фильтрацию в вашем регионе.\n"
            f"Мы рекомендуем переключиться на резервный сервер (🇸🇪 Швеция или 🇧🇾 Беларусь)."
        )
    elif hours_since_sub > 48:
        # Config is older than 2 days (potential mismatch with updated port 8443 or SNI)
        status = 'stale_config'
        diagnosis_title = '🟡 Устаревший конфиг в приложении'
        user_msg = (
            f"⚠️ <b>Конфигурация в приложении устарела!</b>\n\n"
            f"Серверы были переведены на защищённый порт <b>{server.port}</b> для обхода блокировок. "
            f"Ваше приложение не обновляло настройки более {int(hours_since_sub)} ч.\n\n"
            f"👉 <b>Как исправить за 10 секунд:</b>\n"
            f"1. Нажмите <b>«🔄 Обновить подписку»</b> ниже.\n"
            f"2. В приложении нажмите значок круглой стрелочки (обновить список).\n"
            f"3. Переподключите VPN."
        )
    elif up > 5000 and down < 1000:
        # Traffic stall: user sent requests, 0 bytes returned
        status = 'traffic_stall'
        diagnosis_title = '🔴 Зависание трафика (Дроп пакетов)'
        user_msg = (
            f"⚠️ <b>Пакеты уходят, но ответ не возвращается</b>\n\n"
            f"Зафиксирована отправка запросов ({round(up/1024, 1)} КБ), но сервер или провайдер не передаёт ответ.\n\n"
            f"👉 <b>Решение:</b>\n"
            f"1. Нажмите <b>«🔄 Обновить подписку»</b> ниже.\n"
            f"2. Если не помогло — смените сервер на 🇸🇪 Швецию (порт 443)."
        )

    # Save to UserConnectionLog
    log_event = 'complaint'
    if status == 'traffic_stall':
        log_event = 'traffic_stall'
    elif status == 'stale_config':
        log_event = 'stale_config'

    details_str = (
        f"Status: {status} | Diagnosis: {diagnosis_title} | "
        f"Up: {up} B, Down: {down} B | Hours since sub: {hours_since_sub}h"
    )

    UserConnectionLog.objects.create(
        user=user,
        server=server,
        event_type=log_event,
        ip_address=client_ip,
        user_agent=user_agent or "",
        client_type=dev.client_type if dev else "INCY",
        up_bytes=up,
        down_bytes=down,
        details=details_str,
        admin_notified=True
    )

    # Send Instant Notification to Admin in Telegram
    up_display = f"{round(up / 1024, 1)} КБ" if up < 1024*1024 else f"{round(up / (1024**2), 1)} МБ"
    down_display = f"{round(down / 1024, 1)} КБ" if down < 1024*1024 else f"{round(down / (1024**2), 1)} МБ"
    tg_handle = f"@{user.telegram_username}" if user.telegram_username else f"ID {user.telegram_id or '—'}"
    sub_time_str = f"{hours_since_sub} ч назад" if hours_since_sub < 900 else "Никогда / Давно"

    admin_text = (
        f"🚨 <b>ЖАЛОБА / ДИАГНОСТИКА: Не работает VPN!</b>\n\n"
        f"👤 <b>Пользователь:</b> {user.username} ({tg_handle}, User ID: {user.id})\n"
        f"🌐 <b>Сервер:</b> {server.display_name} (<code>{server.ip}:{server.port}</code>)\n"
        f"📡 <b>SNI:</b> <code>{server.reality_sni}</code>\n"
        f"📊 <b>Трафик:</b> Up: {up_display} | Down: {down_display}\n"
        f"🔄 <b>Конфиг в приложении:</b> {sub_time_str}\n"
        f"📱 <b>Устройство:</b> {device_name}\n"
        f"🛠️ <b>Диагноз:</b> {diagnosis_title}"
    )
    notify_admin(admin_text)

    return {
        'status': status,
        'title': diagnosis_title,
        'message': user_msg,
        'server_name': server.clean_name,
        'server_flag': server.flag,
        'sub_url': key.get_sub_url(),
        'happ_url': key.get_happ_url(),
        'incy_url': key.get_incy_url(),
        'vless_url': key.get_vless_url()
    }


def audit_users_connection_health() -> dict:
    """
    Automated background worker (called by check_servers cron every 5 min):
    Inspects 3X-UI SQLite for stalled client sessions (packets sent, 0 received)
    and notifies admin proactively BEFORE the user complains.
    """
    import sqlite3
    db_path = '/etc/x-ui/x-ui.db'
    if not os.path.exists(db_path):
        return {'audited': 0, 'stalls_found': 0}

    try:
        conn = sqlite3.connect(db_path, timeout=4)
        cur = conn.cursor()
        cur.execute("SELECT email, up, down, last_online FROM client_traffics")
        rows = cur.fetchall()
        conn.close()
    except Exception as e:
        logger.warning(f"Could not read client_traffics in audit: {e}")
        return {'audited': 0, 'stalls_found': 0}

    now_ms = int(time.time() * 1000)
    thirty_min_ms = 30 * 60 * 1000
    stalls = 0
    present_emails = set()

    for email, up, down, last_online in rows:
        present_emails.add(email)
        if not last_online or (now_ms - last_online) > thirty_min_ms:
            continue

        up_val = up or 0
        down_val = down or 0

        # Stall condition: Client sent requests/handshake, but received zero/almost zero data back
        is_stall = (up_val > 1500 and down_val < 500) or (up_val > 5000 and (down_val / (up_val + 1)) < 0.1)
        if is_stall:
            parts = email.rsplit('_', 1)
            user = None
            if len(parts) == 2 and parts[1].isdigit():
                user = CustomUser.objects.filter(id=int(parts[1])).first()
            if not user:
                user = CustomUser.objects.filter(username=email).first()

            if not user:
                continue

            # Don't spam: check if we alerted for this user in last 45 min
            recent_alert = UserConnectionLog.objects.filter(
                user=user,
                event_type='traffic_stall',
                created_at__gte=timezone.now() - timezone.timedelta(minutes=45)
            ).exists()

            if recent_alert:
                continue

            key = VPNKey.objects.filter(user=user, is_active=True).first()
            server = key.server if key else VPNServer.objects.filter(is_active=True).first()

            mins_ago = max(1, int((now_ms - last_online) / 60000))
            UserConnectionLog.objects.create(
                user=user,
                server=server,
                event_type='traffic_stall',
                up_bytes=up_val,
                down_bytes=down_val,
                details=f"Auto-Audit detected stall: Up {up_val} B, Down {down_val} B ({mins_ago} min ago)",
                admin_notified=True
            )

            stalls += 1
            admin_msg = (
                f"🔴 <b>АВТО-СКАНЕР: Зависание трафика у пользователя!</b>\n\n"
                f"👤 <b>Пользователь:</b> {user.username} (ID: {user.id})\n"
                f"🌐 <b>Сервер:</b> {server.clean_name if server else '—'} (порт {server.port if server else '—'})\n"
                f"📡 <b>SNI:</b> <code>{server.reality_sni if server else '—'}</code>\n"
                f"📉 <b>Трафик:</b> Up: {round(up_val/1024, 1)} КБ | Down: {round(down_val/1024, 1)} КБ\n"
                f"⏱️ <b>Активность:</b> {mins_ago} мин назад\n"
                f"⚠️ <b>Проблема:</b> Клиент отправляет пакеты, но сервер/провайдер не возвращает данные (дроп соединения)."
            )
            notify_admin(admin_msg)

    # Check for active keys missing in panel inbound
    active_keys = VPNKey.objects.filter(is_active=True, user__balance__gt=0).select_related('user', 'server')
    for k in active_keys:
        expected_email = f"{k.user.username}_{k.user.id}"
        if expected_email not in present_emails and k.server and k.server.panel_url:
            try:
                ensure_key_in_panel(k)
                logger.info(f"Auto-healed missing key for {k.user.username} in {k.server.name}")
            except Exception as e:
                logger.warning(f"Failed to auto-heal key for {k.user.username}: {e}")

    return {'audited': len(rows), 'stalls_found': stalls}





