import logging
import traceback
from django.utils import timezone
from django.contrib.auth import login
from django.shortcuts import render
from django.http import JsonResponse, Http404
from django.conf import settings
from .models import DeviceAuthKey, ErrorIncident

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


class ErrorIncidentMiddleware:
    """
    Fail-Safe Error Interceptor:
    Catches unhandled server exceptions, logs full traceback to rotating log files,
    creates an ErrorIncident DB record with unique incident code, and presents
    a friendly user-facing 500 error page with direct support channels.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_exception(self, request, exception):
        # Do not intercept 404 Http errors here
        if isinstance(exception, Http404):
            return None

        tb_str = traceback.format_exc()
        logger.error(
            f"Unhandled exception on {request.method} {request.path}: {exception}\n{tb_str}"
        )

        try:
            incident = ErrorIncident.create_incident(request, exception, tb_str=tb_str)
            incident_id = incident.incident_id
        except Exception as db_err:
            logger.critical(f"Failed to record ErrorIncident in DB: {db_err}")
            incident_id = "ERR-SYS-UNRECOVERED"

        # If developer explicitly passes ?raw_debug=1 when DEBUG=True, allow normal debug view
        if settings.DEBUG and request.GET.get('raw_debug') == '1':
            return None

        # API / Ajax / JSON requests
        is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'
        is_api = request.path.startswith('/api/') or 'application/json' in request.headers.get('accept', '')

        if is_api or is_ajax:
            return JsonResponse({
                'success': False,
                'error': 'Internal server error',
                'incident_id': incident_id,
                'message': 'Что-то пошло не так. Мы уже получили уведомление об ошибке. '
                           'Вы можете обратиться в поддержку @livedev_by с кодом инцидента.',
                'support': {
                    'telegram': '@livedev_by',
                    'whatsapp': '+79206612923',
                    'phone': '+79206612923'
                }
            }, status=500)

        # Standard HTML request
        context = {
            'incident_id': incident_id,
            'error_message': str(exception),
            'path': request.path,
        }
        return render(request, '500.html', context, status=500)

