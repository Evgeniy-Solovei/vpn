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

    def add_or_update_client(self, key: VPNKey) -> bool:
        """
        Adds or updates client in 3X-UI inbound with dynamic expiryTime.
        If user has NO active subscription or key is inactive, purges client from 3X-UI!
        """
        if not key or not key.user or not key.user.has_active_subscription or not key.is_active:
            self.delete_client(key)
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

        # 1. Try modern 3X-UI add endpoint
        modern_payload = {
            "client": client_settings,
            "inboundIds": [self.server.panel_inbound_id]
        }
        try:
            resp = self.client.post(f"{self.base_url}/panel/api/clients/add", json=modern_payload, cookies=self.cookies, headers=headers)
            if resp.status_code == 200 and resp.json().get('success'):
                logger.info(f"Successfully added client {key.user.username} to 3X-UI")
                return True
        except Exception as e:
            logger.debug(f"Modern 3X-UI clients/add failed, attempting refresh: {e}")

        # 2. If client exists, delete and re-add to ensure fresh expiryTime and enable: True
        try:
            self.delete_client(key)
            resp = self.client.post(f"{self.base_url}/panel/api/clients/add", json=modern_payload, cookies=self.cookies, headers=headers)
            if resp.status_code == 200 and resp.json().get('success'):
                logger.info(f"Successfully refreshed client {email} in 3X-UI with new expiry")
                return True
        except Exception as e:
            logger.debug(f"Re-add client failed: {e}")

        # 3. Fallback to legacy inbounds/addClient
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

    def add_client(self, key: VPNKey) -> bool:
        return self.add_or_update_client(key)

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
                logger.info(f"Successfully deleted client {email} from 3X-UI")
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


def get_incy_routing_dict(key=None) -> dict:
    """
    Generates dynamic routing JSON profile for INCY application.
    Uses reliable UDP DNS (77.88.8.8 and 1.1.1.1) to eliminate DoH handshake failures.
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

        # Active direct zones configured for this key (default: ru, by, su, рф)
        active_zones = key.get_direct_zones() if (key and hasattr(key, 'get_direct_zones')) else ['ru', 'by', 'su', 'рф', 'xn--p1ai']
        for z in active_zones:
            if z in ('ru',):
                direct_sites.extend(["domain:ru", "domain:com.ru", "domain:net.ru", "domain:org.ru", "domain:msk.ru", "domain:spb.ru"])
            elif z in ('by',):
                direct_sites.extend(["domain:by", "domain:gov.by", "domain:mil.by"])
            elif z in ('su',):
                direct_sites.append("domain:su")
            elif z in ('рф', 'xn--p1ai'):
                direct_sites.append("domain:xn--p1ai")
            else:
                direct_sites.append(f"domain:{z}")

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
            # Bitrix24 Ecosystem (Bitrix24 cloud portals, CRM, mobile app)
            "domain:bitrix24.ru",
            "domain:bitrix24.by",
            "domain:bitrix24.com",
            "domain:bitrix24.kz",
            "domain:b24.by",
            "domain:b24-am.com",
            "domain:bitrix.info",
            "domain:bitrix.cloud",
            "domain:bitrix24.site",
            "domain:1c-bitrix.ru",
            "domain:bitrix.ru",
            "domain:bx.vc",
            "domain:bitrix24.net",
            "domain:bitrix24.eu",
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
            "domain:esia.gosuslugi.ru",
            "domain:pgu.mos.ru",
            "domain:nalog.ru",
            "domain:nalog.gov.ru",
            "domain:mos.ru",
            "domain:pbr.ru",
            "domain:cbr.ru",
            "domain:customs.gov.ru",
            "domain:fssp.gov.ru",
            "domain:mvd.ru",
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
            "10.0.0.0/8",
            "172.16.0.0/12",
            "192.168.0.0/16",
            "127.0.0.0/8",
            "169.254.0.0/16",
            "::1/128",
            "fc00::/7",
            "fe80::/10",
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
            # T-Bank (AS41994)
            "91.194.226.0/23",
            "185.148.80.0/22",
            # Alfa-Bank (AS15944)
            "217.12.96.0/20",
        ]
        route_order = "block-proxy-direct" if (key and hasattr(key, 'get_custom_proxy_domains') and key.get_custom_proxy_domains()) else "block-direct-proxy"
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
        route_order = "block-proxy-direct"
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
        "RemoteDNSIP": "1.1.1.1",
        "RemoteDns": "1.1.1.1",
        "DomesticDNSType": "DoU",
        "DomesticDNSDomain": "",
        "DomesticDNSIP": "77.88.8.8",
        "DomesticDns": "77.88.8.8",
        "Geoipurl": "https://github.com/Loyalsoldier/v2ray-rules-dat/releases/latest/download/geoip.dat",
        "Geositeurl": "https://github.com/Loyalsoldier/v2ray-rules-dat/releases/latest/download/geosite.dat",
        "LastUpdated": str(int(time.time())),
        "DnsHosts": {},
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
            # OpenAI / ChatGPT
            "104.18.0.0/15", "172.64.0.0/13", "23.96.0.0/13", "20.0.0.0/11",
            # Discord
            "162.158.0.0/15", "66.22.196.0/22", "66.22.200.0/22", "66.22.204.0/22", "66.22.208.0/20",
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
                if svc.add_client(key):
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




