import logging
import hmac
import hashlib
import urllib.parse
import urllib.request
import json
import secrets
from django.shortcuts import render, redirect
from django.urls import reverse
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.contrib.auth.tokens import default_token_generator
from django.conf import settings
from django.http import JsonResponse

from decimal import Decimal
from .models import CustomUser, DeviceAuthKey, TelegramLinkCode, MagicLoginToken
from .forms import RegisterForm, LoginForm, PasswordResetRequestForm, SetNewPasswordForm
from apps.vpn.models import VPNServer, VPNKey
from apps.vpn.services import get_or_create_default_server

logger = logging.getLogger(__name__)

def apply_persistent_auth(request, response, user, remember=True, days=90):
    """
    Caches authentication for 90 days.
    Sets 90-day session expiry and attaches a persistent 90-day DeviceAuthKey cookie.
    Uses SameSite=None + Secure=True on HTTPS for seamless Telegram WebView support.
    """
    cookie_name = getattr(settings, 'DEVICE_KEY_COOKIE_NAME', 'vpn_device_key')
    if remember:
        request.session.set_expiry(days * 24 * 3600)
        device_key = DeviceAuthKey.issue_key(user, request=request, days=days)
        is_sec = request.is_secure()
        response.set_cookie(
            cookie_name,
            device_key.key,
            max_age=days * 24 * 3600,
            httponly=True,
            samesite='None' if is_sec else 'Lax',
            secure=is_sec
        )
        logger.info(f"Issued 90-day device key for {user.username}")
    else:
        request.session.set_expiry(0)
    return response

def register_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    email_already_exists = False
    existing_email = ''

    if request.method == 'POST':
        form = RegisterForm(request.POST)
        ref_code = request.GET.get('ref') or request.POST.get('ref')
        
        if form.is_valid():
            user = form.save(commit=False)
            user.balance = Decimal('3.50')  # 1-day free trial on web registration
            user.telegram_bonus_claimed = False
            if ref_code:
                try:
                    referrer = CustomUser.objects.get(referral_code=ref_code)
                    user.referred_by = referrer
                    # Bonus for referrer
                    referrer.balance += 10
                    referrer.save()
                except CustomUser.DoesNotExist:
                    pass
            user.save()

            # Ensure default active VPN key is created
            try:
                server = get_or_create_default_server()
                VPNKey.objects.get_or_create(user=user, server=server)
            except Exception as e:
                logger.error(f"Error provisioning initial VPN key: {e}")

            login(request, user)
            messages.success(request, f"Добро пожаловать, {user.username}! Вам начислен пробный баланс.")
            response = redirect('dashboard')
            return apply_persistent_auth(request, response, user, remember=True, days=90)
        else:
            if 'email' in form.errors:
                for err in form.errors['email'].as_data():
                    if err.code == 'email_exists':
                        email_already_exists = True
                        existing_email = request.POST.get('email', '')
    else:
        form = RegisterForm()

    return render(request, 'accounts/register.html', {
        'form': form,
        'email_already_exists': email_already_exists,
        'existing_email': existing_email
    })


def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        form = LoginForm(request.POST)
        if form.is_valid():
            user = form.cleaned_data['user']
            remember_me = form.cleaned_data.get('remember_me', True)
            login(request, user)
            next_url = request.GET.get('next', 'dashboard')
            response = redirect(next_url)
            return apply_persistent_auth(request, response, user, remember=remember_me, days=90)
    else:
        form = LoginForm(initial={'remember_me': True})

    return render(request, 'accounts/login.html', {'form': form})


def logout_view(request):
    cookie_name = getattr(settings, 'DEVICE_KEY_COOKIE_NAME', 'vpn_device_key')
    device_key_val = request.COOKIES.get(cookie_name)
    if device_key_val:
        DeviceAuthKey.objects.filter(key=device_key_val).delete()
    logout(request)
    response = redirect('login')
    response.delete_cookie(cookie_name)
    response.delete_cookie(getattr(settings, 'SESSION_COOKIE_NAME', 'vpn_sessionid'))
    return response


def password_reset_request_view(request):
    initial_email = request.GET.get('email', '')
    if request.method == 'POST':
        form = PasswordResetRequestForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email'].strip().lower()
            users = CustomUser.objects.filter(email__iexact=email)
            if users.exists():
                user = users.first()
                token = default_token_generator.make_token(user)
                uid = urlsafe_base64_encode(force_bytes(user.pk))
                
                reset_link = f"{settings.SITE_URL}/auth/password-reset-confirm/{uid}/{token}/"
                
                subject = "Восстановление пароля — VPN Live Dev"
                message_html = render_to_string('accounts/emails/password_reset_email.html', {
                    'user': user,
                    'reset_link': reset_link,
                    'domain': settings.DOMAIN,
                })
                
                try:
                    send_mail(
                        subject=subject,
                        message=f"Перейдите по ссылке для сброса пароля: {reset_link}",
                        from_email=settings.DEFAULT_FROM_EMAIL,
                        recipient_list=[user.email],
                        html_message=message_html,
                        fail_silently=False
                    )
                except Exception as e:
                    logger.error(f"Error sending email: {e}")

                if getattr(settings, 'DEBUG', False):
                    request.session['debug_reset_link'] = reset_link
            
            # Show the same confirmation screen regardless of user existence (security best practice)
            return redirect('password_reset_done')
    else:
        form = PasswordResetRequestForm(initial={'email': initial_email})

    return render(request, 'accounts/password_reset_request.html', {'form': form})


def password_reset_done_view(request):
    debug_reset_link = request.session.pop('debug_reset_link', None) if getattr(settings, 'DEBUG', False) else None
    return render(request, 'accounts/password_reset_done.html', {'debug_reset_link': debug_reset_link})


def password_reset_confirm_view(request, uidb64, token):
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = CustomUser.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, CustomUser.DoesNotExist):
        user = None

    if user is not None and default_token_generator.check_token(user, token):
        if request.method == 'POST':
            form = SetNewPasswordForm(request.POST)
            if form.is_valid():
                user.set_password(form.cleaned_data['new_password'])
                user.save()
                login(request, user)
                messages.success(request, "Ваш пароль успешно изменен!")
                response = redirect('dashboard')
                return apply_persistent_auth(request, response, user, remember=True, days=90)
        else:
            form = SetNewPasswordForm()
        return render(request, 'accounts/password_reset_confirm.html', {'form': form, 'validlink': True})
    else:
        return render(request, 'accounts/password_reset_confirm.html', {'validlink': False})


def dashboard_view(request):
    if not request.user.is_authenticated:
        if request.GET.get('tg') == '1':
            return redirect('miniapp')
        return redirect(f"{settings.LOGIN_URL}?next={request.get_full_path()}")

    user = request.user
    
    # Get or create VPN key (preserve selected server)
    key = VPNKey.objects.filter(user=user).first()
    if not key:
        server = get_or_create_default_server()
        key = VPNKey.objects.create(user=user, server=server)

    from apps.vpn.services import ensure_key_in_panel
    try:
        ensure_key_in_panel(key)
    except Exception:
        pass
    
    # Auto-failover if user's current server became inactive or blocked by RKN
    if not key.server.is_active or key.server.health_status == 'blocked_rkn':
        healthy = VPNServer.objects.filter(is_active=True).exclude(health_status='blocked_rkn').order_by('order', 'ping_ms').first()
        if healthy:
            key.server = healthy
            key.save(update_fields=['server', 'updated_at'])

    servers = VPNServer.objects.filter(is_active=True).exclude(health_status='blocked_rkn').order_by('order', 'ping_ms')
    referrals_count = user.referrals.count()
    referral_url = f"{settings.SITE_URL}/auth/register/?ref={user.referral_code}"

    # Handle payment return redirects (YooKassa / bePaid)
    payment_status = request.GET.get('payment')
    order_id = request.GET.get('order')
    if payment_status == 'yookassa_success' and order_id:
        from apps.billing.models import YooKassaOrder
        order = YooKassaOrder.objects.filter(order_id=order_id, user=user).first()
        if order:
            if order.status == YooKassaOrder.Status.PAID:
                messages.success(request, f"🎉 Оплата {order.amount_rub} ₽ через ЮKassa успешно зачислена! Добавлено +{order.days} дн. доступа.")
            else:
                shop_id = getattr(settings, 'YOOKASSA_SHOP_ID', '')
                secret_key = getattr(settings, 'YOOKASSA_SECRET_KEY', '')
                if shop_id and secret_key and order.payment_id:
                    try:
                        import httpx
                        with httpx.Client(timeout=4.0) as client:
                            resp = client.get(
                                f"https://api.yookassa.ru/v3/payments/{order.payment_id}",
                                auth=(str(shop_id), str(secret_key)),
                                headers={'Accept': 'application/json'}
                            )
                            if resp.status_code == 200 and resp.json().get('status') == 'succeeded':
                                order.complete_payment()
                                messages.success(request, f"🎉 Оплата {order.amount_rub} ₽ через ЮKassa успешно зачислена! Добавлено +{order.days} дн. доступа.")
                            else:
                                messages.info(request, "Платёж через ЮKassa принят и обрабатывается банком.")
                    except Exception as e:
                        logger.warning("Error checking YooKassa status on return: %s", e)
                        messages.info(request, "Платёж через ЮKassa обрабатывается банком.")
                else:
                    messages.info(request, "Платёж через ЮKassa принят в обработку.")
    elif payment_status == 'success':
        messages.success(request, "🎉 Оплата через bePaid успешно принята! Баланс пополнен.")
    elif payment_status in ('failed', 'cancelled'):
        messages.warning(request, "Платёж был отменён или не завершён. Средства не списаны.")

    return render(request, 'accounts/dashboard.html', {
        'user': user,
        'vpn_key': key,
        'servers': servers,
        'referrals_count': referrals_count,
        'referral_url': referral_url,
        'is_telegram_linked': bool(user.telegram_id),
        'can_claim_tg_bonus': not user.telegram_bonus_claimed,
        'bot_username': getattr(settings, 'BOT_USERNAME', 'live_vpn_bot'),
    })


@login_required
def generate_telegram_link_code_view(request):
    """
    Generates a 16-character authorization link code for the current web user
    to link their Telegram account in @live_vpn_bot and receive +2 free days.
    """
    code_obj = TelegramLinkCode.create_for_user(request.user)
    bot_username = getattr(settings, 'BOT_USERNAME', 'live_vpn_bot')
    bot_url = f"https://t.me/{bot_username}?start=link_{code_obj.code}"

    return JsonResponse({
        'success': True,
        'code': code_obj.code,
        'bot_url': bot_url,
        'is_linked': bool(request.user.telegram_id),
        'telegram_username': request.user.telegram_username or '',
        'bonus_claimed': request.user.telegram_bonus_claimed,
    })


def magic_login_view(request, token):
    """
    One-click instant login via single-use token issued by Telegram Bot.
    Enables seamless transition from phone/bot to PC without passwords.
    """
    token_obj = MagicLoginToken.objects.select_related('user').filter(token=token).first()
    if not token_obj or not token_obj.is_valid():
        messages.error(request, "Срок действия ссылки для входа истек или она уже была использована. Запросите новую ссылку в Telegram-боте.")
        return redirect('login')

    user = token_obj.user
    token_obj.delete()  # Single-use

    login(request, user, backend='django.contrib.auth.backends.ModelBackend')
    messages.success(request, f"Добро пожаловать, {user.username}! Вы успешно вошли через Telegram.")
    response = redirect('dashboard')
    return apply_persistent_auth(request, response, user, remember=True, days=90)


def telegram_auth_callback_view(request):
    """
    Handles official Telegram Login Widget callback.
    Authenticates user, creates account if needed, or links Telegram to current session.
    """
    auth_data = dict(request.GET.items())
    check_hash = auth_data.get('hash')
    if not check_hash:
        messages.error(request, "Некорректные данные авторизации Telegram.")
        return redirect('login')

    bot_token = getattr(settings, 'BOT_TOKEN', '')
    if not bot_token:
        messages.error(request, "Telegram-авторизация временно недоступна.")
        return redirect('login')

    # Verify Telegram signature
    data_check = []
    for k, v in sorted(auth_data.items()):
        if k != 'hash':
            data_check.append(f"{k}={v}")
    data_check_string = "\n".join(data_check)
    secret_key = hashlib.sha256(bot_token.encode()).digest()
    expected_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(expected_hash, check_hash):
        messages.error(request, "Ошибка проверки подлинности данных Telegram.")
        return redirect('login')

    telegram_id = str(auth_data.get('id', '')).strip()
    telegram_username = (auth_data.get('username') or '').strip()
    first_name = (auth_data.get('first_name') or '').strip()

    # Scenario 1: User is already logged in on website and linking Telegram
    if request.user.is_authenticated:
        user = request.user
        existing = CustomUser.objects.filter(telegram_id=telegram_id).exclude(id=user.id).first()
        if existing:
            messages.warning(request, f"Этот Telegram-аккаунт уже привязан к пользователю {existing.username}.")
            return redirect('dashboard')

        user.telegram_id = telegram_id
        if telegram_username:
            user.telegram_username = telegram_username
        if not user.telegram_bonus_claimed:
            user.telegram_bonus_claimed = True
            user.balance += Decimal("7.00")  # +2 days bonus
            messages.success(request, "🎉 Telegram успешно привязан! Вам начислено +2 дня бесплатного VPN (+7.00 ₽).")
        else:
            messages.success(request, "Telegram успешно привязан к вашему аккаунту.")
        user.save()
        return redirect('dashboard')

    # Scenario 2: User logging in via Telegram widget
    user = CustomUser.objects.filter(telegram_id=telegram_id).first()
    if not user and telegram_username:
        user = CustomUser.objects.filter(username=telegram_username).first()
        if user and not user.telegram_id:
            user.telegram_id = telegram_id
            user.save()

    if not user:
        # Create new user for Telegram visitor
        base_username = telegram_username or f"tg_{telegram_id}"
        username = base_username
        counter = 1
        while CustomUser.objects.filter(username=username).exists():
            username = f"{base_username}_{counter}"
            counter += 1

        user = CustomUser.objects.create(
            username=username,
            telegram_id=telegram_id,
            telegram_username=telegram_username,
            first_name=first_name,
            balance=Decimal("10.50"),  # 3 days trial
            daily_deduction=Decimal("3.50"),
            telegram_bonus_claimed=True,
        )
        user.set_unusable_password()
        user.save()

        # Generate VPNKey
        from apps.vpn.models import VPNKey
        from apps.vpn.services import get_or_create_default_server, ThreeXUIService
        server = get_or_create_default_server()
        key = VPNKey.objects.create(
            user=user,
            server=server,
            traffic_limit_gb=200,
            max_devices=5,
        )
        try:
            service = ThreeXUIService(server)
            service.add_client(key)
        except Exception:
            pass

        messages.success(request, f"Добро пожаловать в VPN live-dev! Вам начислено 3 дня бесплатного доступа.")

    login(request, user, backend='django.contrib.auth.backends.ModelBackend')
    response = redirect('dashboard')
    return apply_persistent_auth(request, response, user, remember=True, days=90)


def google_login_view(request):
    """
    Initiates Google OAuth 2.0 authorization redirect.
    """
    client_id = getattr(settings, 'GOOGLE_CLIENT_ID', '').strip()
    if not client_id:
        messages.info(
            request,
            "Для входа через Google требуется настроить GOOGLE_CLIENT_ID в конфигурации. "
            "Пока вы можете мгновенно войти через Telegram без пароля!"
        )
        return redirect('login')

    state = secrets.token_urlsafe(16)
    request.session['google_oauth_state'] = state

    redirect_uri = request.build_absolute_uri(reverse('google_callback'))
    if request.is_secure() or getattr(settings, 'SECURE_PROXY_SSL_HEADER', None):
        redirect_uri = redirect_uri.replace('http://', 'https://')

    params = {
        'client_id': client_id,
        'redirect_uri': redirect_uri,
        'response_type': 'code',
        'scope': 'openid email profile',
        'state': state,
        'prompt': 'select_account',
    }
    google_auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{urllib.parse.urlencode(params)}"
    return redirect(google_auth_url)


def google_callback_view(request):
    """
    Handles Google OAuth 2.0 authorization code exchange and user login.
    """
    code = request.GET.get('code')
    state = request.GET.get('state')
    saved_state = request.session.pop('google_oauth_state', None)

    if not code:
        error = request.GET.get('error', 'Авторизация через Google была отменена.')
        messages.error(request, f"Вход через Google: {error}")
        return redirect('login')

    if not state or state != saved_state:
        messages.error(request, "Ошибка безопасности сессии (state mismatch). Пожалуйста, попробуйте снова.")
        return redirect('login')

    client_id = getattr(settings, 'GOOGLE_CLIENT_ID', '').strip()
    client_secret = getattr(settings, 'GOOGLE_CLIENT_SECRET', '').strip()

    if not client_id or not client_secret:
        messages.error(request, "Google OAuth не настроен на сервере.")
        return redirect('login')

    redirect_uri = request.build_absolute_uri(reverse('google_callback'))
    if request.is_secure() or getattr(settings, 'SECURE_PROXY_SSL_HEADER', None):
        redirect_uri = redirect_uri.replace('http://', 'https://')

    # Exchange code for tokens
    token_url = "https://oauth2.googleapis.com/token"
    token_data = urllib.parse.urlencode({
        'code': code,
        'client_id': client_id,
        'client_secret': client_secret,
        'redirect_uri': redirect_uri,
        'grant_type': 'authorization_code',
    }).encode('utf-8')

    try:
        req = urllib.request.Request(token_url, data=token_data, headers={'User-Agent': 'VPNLiveDev/1.0'})
        with urllib.request.urlopen(req, timeout=10) as resp:
            token_resp = json.loads(resp.read().decode('utf-8'))
            access_token = token_resp.get('access_token')
    except Exception as e:
        logger.error(f"Failed to exchange code for Google token: {e}")
        messages.error(request, "Не удалось получить токен доступа Google. Попробуйте еще раз.")
        return redirect('login')

    if not access_token:
        messages.error(request, "Google не вернул access_token.")
        return redirect('login')

    # Fetch user info
    userinfo_url = "https://www.googleapis.com/oauth2/v3/userinfo"
    try:
        userinfo_req = urllib.request.Request(userinfo_url, headers={
            'Authorization': f'Bearer {access_token}',
            'User-Agent': 'VPNLiveDev/1.0'
        })
        with urllib.request.urlopen(userinfo_req, timeout=10) as resp:
            user_info = json.loads(resp.read().decode('utf-8'))
    except Exception as e:
        logger.error(f"Failed to fetch Google userinfo: {e}")
        messages.error(request, "Не удалось получить данные профиля Google.")
        return redirect('login')

    google_sub = user_info.get('sub')
    email = (user_info.get('email') or '').lower().strip()
    name = user_info.get('name') or user_info.get('given_name') or ''

    if not email:
        messages.error(request, "Google не предоставил email для вашего аккаунта.")
        return redirect('login')

    # Scenario 1: User already logged in and linking Google
    if request.user.is_authenticated:
        user = request.user
        existing = CustomUser.objects.filter(google_id=google_sub).exclude(id=user.id).first()
        if existing:
            messages.warning(request, f"Этот Google-аккаунт уже привязан к пользователю {existing.username}.")
            return redirect('dashboard')
        user.google_id = google_sub
        user.save()
        messages.success(request, f"Google-аккаунт {email} успешно привязан!")
        return redirect('dashboard')

    # Scenario 2: Login or Register
    user = CustomUser.objects.filter(google_id=google_sub).first()
    if not user:
        user = CustomUser.objects.filter(email__iexact=email).first()
        if user:
            user.google_id = google_sub
            user.save()

    if not user:
        # Create new user
        base_username = email.split('@')[0].replace('.', '_').replace('-', '_')
        username = base_username
        counter = 1
        while CustomUser.objects.filter(username=username).exists():
            username = f"{base_username}_{counter}"
            counter += 1

        user = CustomUser.objects.create(
            username=username,
            email=email,
            first_name=name,
            google_id=google_sub,
            balance=Decimal('10.50'),  # 3 days free trial
            daily_deduction=Decimal('3.50'),
        )
        user.set_unusable_password()
        user.save()

        # Create VPN key
        from apps.vpn.models import VPNKey
        from apps.vpn.services import get_or_create_default_server, ThreeXUIService
        server = get_or_create_default_server()
        key = VPNKey.objects.create(
            user=user,
            server=server,
            traffic_limit_gb=200,
            max_devices=5,
        )
        try:
            service = ThreeXUIService(server)
            service.add_client(key)
        except Exception:
            pass

        messages.success(request, f"Добро пожаловать в VPN live-dev! Вам начислено 3 дня бесплатного доступа.")

    login(request, user, backend='django.contrib.auth.backends.ModelBackend')
    response = redirect('dashboard')
    return apply_persistent_auth(request, response, user, remember=True, days=90)


def custom_500_handler(request):
    import secrets
    from datetime import datetime
    incident_id = getattr(request, '_incident_id', None)
    if not incident_id:
        incident_id = f"ERR-500-{secrets.token_hex(3).upper()}-{datetime.now().strftime('%Y%m%d')}"
    return render(request, '500.html', {'incident_id': incident_id}, status=500)


def custom_404_handler(request, exception=None):
    if request.path.startswith('/api/'):
        return JsonResponse({
            'success': False,
            'error': 'Not Found',
            'message': 'Запрашиваемый ресурс не найден.'
        }, status=404)
    return render(request, '404.html', status=404)


