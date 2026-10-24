from django.conf import settings

def site_settings(request):
    site_url = getattr(settings, 'SITE_URL', 'https://vpn.live-dev.by').rstrip('/')
    if request.is_secure() or getattr(settings, 'SECURE_PROXY_SSL_HEADER', None):
        site_url = site_url.replace('http://', 'https://')
    return {
        'SITE_DOMAIN': getattr(settings, 'DOMAIN', 'vpn.live-dev.by'),
        'SITE_URL': site_url,
        'BOT_USERNAME': getattr(settings, 'BOT_USERNAME', 'live_vpn_bot'),
        'GOOGLE_CLIENT_ID': getattr(settings, 'GOOGLE_CLIENT_ID', ''),
        'ADMIN_URL_PATH': getattr(settings, 'ADMIN_URL_PATH', 'management-hq').strip('/'),
    }
