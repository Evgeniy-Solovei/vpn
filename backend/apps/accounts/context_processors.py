from django.conf import settings

def site_settings(request):
    return {
        'SITE_DOMAIN': getattr(settings, 'DOMAIN', 'vpn.live-dev.by'),
        'SITE_URL': getattr(settings, 'SITE_URL', 'http://vpn.live-dev.by'),
        'BOT_USERNAME': getattr(settings, 'BOT_USERNAME', 'vpn_livedev_bot'),
    }
