import logging
from django.utils import timezone
from django.contrib.auth import login
from .models import DeviceAuthKey

logger = logging.getLogger(__name__)

class PersistentAuthMiddleware:
    """
    Middleware for 90-day cached authentication (Device Key).
    Automatically restores user login across browser sessions even if session cookie
    was cleared or expired, as long as valid 90-day device key cookie exists.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not getattr(request, 'user', None) or not request.user.is_authenticated:
            device_key_val = request.COOKIES.get('vpn_device_key')
            if device_key_val:
                try:
                    device_key = DeviceAuthKey.objects.select_related('user').filter(
                        key=device_key_val,
                        expires_at__gt=timezone.now()
                    ).first()

                    if device_key and device_key.user.is_active:
                        # Log user into current session
                        login(request, device_key.user, backend='django.contrib.auth.backends.ModelBackend')
                        request.session.set_expiry(90 * 24 * 3600)
                        logger.info(f"Auto-authenticated user {device_key.user.username} via 90-day device key.")
                except Exception as e:
                    logger.warning(f"Error in PersistentAuthMiddleware: {e}")

        response = self.get_response(request)
        return response
