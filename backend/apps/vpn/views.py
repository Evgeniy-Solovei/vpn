import base64
import io
try:
    import qrcode
    HAS_QRCODE = True
except ImportError:
    HAS_QRCODE = False
from django.http import HttpResponse, JsonResponse, Http404
from django.shortcuts import get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from .models import VPNKey, VPNServer
from .services import generate_pac_script, ThreeXUIService

def subscription_view(request, token):
    """
    Standard Base64 subscription endpoint for INCY, Happ, Hiddify, v2rayNG, etc.
    URL: /sub/<token>
    """
    key = get_object_or_404(VPNKey, sub_token=token)
    user = key.user

    # If user has no active balance
    if not user.has_active_subscription:
        return HttpResponse(
            "# Subscription expired. Please top up your balance at http://vpn.live-dev.by",
            content_type="text/plain; charset=utf-8",
            status=402
        )

    # Collect active servers
    servers = VPNServer.objects.filter(is_active=True)
    vless_links = []
    for s in servers:
        temp_key = key
        # generate link for each server
        tag = f"LiveDev-{s.country_code}-{user.username}"
        vless_link = (
            f"vless://{key.key_uuid}@{s.ip}:{s.port}"
            f"?type=tcp"
            f"&security=reality"
            f"&pbk={s.reality_pbk}"
            f"&fp=chrome"
            f"&sni={s.reality_sni}"
            f"&sid={s.reality_short_id}"
            f"&spx=%2F"
            f"&flow=xtls-rprx-vision"
            f"#{tag}"
        )
        vless_links.append(vless_link)

    # Standard format is base64 encoded newline-separated links
    raw_content = "\n".join(vless_links)
    encoded_content = base64.b64encode(raw_content.encode('utf-8')).decode('utf-8')

    response = HttpResponse(encoded_content, content_type="text/plain; charset=utf-8")
    response['profile-update-interval'] = '12'
    response['content-disposition'] = f'attachment; filename="vpn-livedev-{user.username}.txt"'
    
    # Subscription info header: upload=0; download=0; total=100GB; expire=timestamp
    days_seconds = user.days_left * 86400
    response['subscription-userinfo'] = f"upload=0; download=10485760; total=107374182400; expire={days_seconds}"
    return response


def pac_view(request, token):
    """
    Proxy Auto-Config (PAC) endpoint for connection without installing applications.
    URL: /vpn/pac/<token>
    """
    key = get_object_or_404(VPNKey, sub_token=token)
    pac_content = generate_pac_script(key.server, key.whitelist_enabled, key.get_custom_domains())
    return HttpResponse(pac_content, content_type="application/x-ns-proxy-autoconfig")


def qr_code_view(request, token):
    """Generates a dynamic QR code for the VPN key or subscription URL."""
    key = get_object_or_404(VPNKey, sub_token=token)
    sub_url = key.get_sub_url()

    if HAS_QRCODE:
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=10,
            border=3,
        )
        qr.add_data(sub_url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="#10b981", back_color="#0a0b0e")

        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        return HttpResponse(buffer.getvalue(), content_type="image/png")
    else:
        # Fallback SVG
        svg_content = f'''<svg xmlns="http://www.w3.org/2000/svg" width="220" height="220" viewBox="0 0 220 220">
          <rect width="220" height="220" fill="#0a0b0e" rx="10"/>
          <text x="50%" y="45%" text-anchor="middle" fill="#10b981" font-size="14" font-family="sans-serif" font-weight="bold">VPN QR CODE</text>
          <text x="50%" y="60%" text-anchor="middle" fill="#94a3b8" font-size="11" font-family="sans-serif">Install qrcode in Docker</text>
        </svg>'''
        return HttpResponse(svg_content, content_type="image/svg+xml")


@login_required
def toggle_whitelist_view(request):
    """Toggle Russian Whitelist (Direct routing for RU/RB domains)."""
    if request.method == 'POST':
        key = VPNKey.objects.filter(user=request.user).first()
        if key:
            key.whitelist_enabled = not key.whitelist_enabled
            key.save()
            return JsonResponse({
                'success': True,
                'whitelist_enabled': key.whitelist_enabled,
                'message': "Белый список РФ успешно изменен"
            })
    return JsonResponse({'success': False}, status=400)


@login_required
def regenerate_key_view(request):
    """Regenerate user's UUID / key."""
    if request.method == 'POST':
        key = VPNKey.objects.filter(user=request.user).first()
        if key:
            import uuid
            old_uuid = key.key_uuid
            key.key_uuid = uuid.uuid4()
            key.save()
            
            # Sync with 3X-UI if configured
            try:
                service = ThreeXUIService(key.server)
                service.delete_client(key)
                service.add_client(key)
            except Exception:
                pass

            return JsonResponse({
                'success': True,
                'new_uuid': str(key.key_uuid),
                'vless_url': key.get_vless_url(),
                'sub_url': key.get_sub_url(),
                'incy_url': key.get_incy_url(),
                'message': "Ключ успешно обновлен"
            })
    return JsonResponse({'success': False}, status=400)


def incy_redirect_view(request, token):
    """Landing and redirect view for 1-click import into INCY client."""
    from django.shortcuts import render
    key = get_object_or_404(VPNKey, sub_token=token)
    return render(request, 'vpn/connect.html', {
        'key': key,
        'incy_url': key.get_incy_url(),
        'vless_url': key.get_vless_url(),
        'sub_url': key.get_sub_url(),
    })
