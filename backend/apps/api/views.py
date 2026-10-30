import json
import logging
from decimal import Decimal
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from django.contrib.auth import login as auth_login
from apps.accounts.models import CustomUser, TelegramLinkCode, MagicLoginToken
from apps.vpn.models import VPNServer, VPNKey
from apps.vpn.services import get_or_create_default_server
from apps.billing.models import TariffPlan, Transaction, SubscriptionPackage

logger = logging.getLogger(__name__)


def build_user_response(user, is_new=False):
    try:
        user.apply_daily_deductions()
    except Exception:
        pass

    key = VPNKey.objects.filter(user=user).first()
    if not key:
        server = get_or_create_default_server()
        key, _ = VPNKey.objects.get_or_create(user=user, server=server)
    else:
        server = key.server

    from apps.vpn.services import sync_key_traffic, get_user_devices_info, reset_user_devices
    try:
        sync_key_traffic(key)
        user.sync_vpn_access()
    except Exception:
        pass

    devices_info = get_user_devices_info(user, key=key)

    site_url = getattr(settings, 'SITE_URL', 'http://vpn.live-dev.by')
    referral_url = f"{site_url}/auth/register/?ref={user.referral_code}"
    bot_username = getattr(settings, 'BOT_USERNAME', 'live_vpn_bot')
    bot_referral_url = f"https://t.me/{bot_username}?start=ref_{user.referral_code}"

    return {
        'success': True,
        'is_new': is_new,
        'user': {
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'telegram_id': user.telegram_id,
            'balance': float(user.balance),
            'daily_deduction': float(user.daily_deduction),
            'days_left': user.days_left,
            'autopay': user.autopay,
            'referral_code': user.referral_code,
            'referral_url': referral_url,
            'bot_referral_url': bot_referral_url,
            'referrals_count': user.referrals.count(),
        },
        'devices': devices_info,
        'vpn': {
            'server_id': server.id,
            'server_name': server.display_name,
            'clean_name': server.clean_name,
            'city': server.city,
            'country_code': server.country_code,
            'country_name': server.country_name,
            'flag': server.flag,
            'ping_ms': server.ping_ms,
            'load_percent': server.load_percent,
            'speed_description': server.speed_description,
            'max_devices': getattr(key, 'max_devices', 5) or 5,
            'vless_url': key.get_vless_url(),
            'sub_url': key.get_sub_url(),
            'incy_url': key.get_incy_url(),
            'routing_deeplink': key.get_incy_routing_deeplink(),
            'routing_url': key.get_routing_url(),
            'connect_url': key.get_connect_url(),
            'whitelist_enabled': key.whitelist_enabled,
            'custom_whitelist': key.custom_whitelist,
            'custom_domains': key.get_custom_domains(),
            'qr_url': f"{site_url}/vpn/qr/{key.sub_token}/",
            'pac_url': f"{site_url}/vpn/pac/{key.sub_token}/",
        },
        'packages': [
            {
                'id': p.id,
                'name': p.name,
                'days': p.days,
                'price_rub': float(p.price_rub),
                'price_byn': float(p.price_byn),
                'daily_rub': float(p.daily_rub),
                'badge': p.badge,
                'is_featured': p.is_featured,
            }
            for p in SubscriptionPackage.get_active_packages()
        ],
        'traffic': {
            'used_bytes': key.used_traffic_bytes,
            'used_display': key.traffic_display,
            'used_gb': key.used_traffic_gb,
            'limit_gb': key.traffic_limit_gb or 150,
            'is_unlimited': False,
            'percent': key.traffic_percent,
            'left_gb': key.traffic_left_gb,
            'reset_date': key.traffic_reset_date.strftime('%d.%m.%Y') if key.traffic_reset_date else None,
            'is_throttled': key.is_throttled,
            'current_speed': f"{key.current_speed_mbps} Мб/с",
        }
    }




def user_profile_api(request):
    """
    Get profile and VPN details of currently authenticated web session user.
    Used by web frontend and Telegram Mini App browser preview.
    """
    if not request.user.is_authenticated:
        return JsonResponse({'success': False, 'authenticated': False, 'message': 'Не авторизован'}, status=200)

    data = build_user_response(request.user)
    data['authenticated'] = True
    return JsonResponse(data)


@csrf_exempt
def demo_login_api(request):
    """
    One-click authentication as Demo user for testing and local preview.
    """
    demo_user = CustomUser.objects.filter(username='demo').first()
    if not demo_user:
        server = get_or_create_default_server()
        demo_user = CustomUser.objects.create_user(
            username='demo',
            email='demo@live-dev.by',
            password='demo123',
            balance=Decimal('105.00'),
            daily_deduction=Decimal('3.50')
        )
        VPNKey.objects.get_or_create(user=demo_user, server=server)

    auth_login(request, demo_user)
    data = build_user_response(demo_user)
    data['authenticated'] = True
    response = JsonResponse(data)
    from apps.accounts.views import apply_persistent_auth
    return apply_persistent_auth(request, response, demo_user, remember=True, days=90)


@csrf_exempt
def tg_sync_view(request):
    """
    Sync endpoint for Telegram Bot and Telegram Mini App.
    Accepts telegram_id, telegram_username, ref_code.
    Creates or fetches user, provides their VPN key, balance, and settings.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    try:
        data = json.loads(request.body.decode('utf-8')) if request.body else {}
        telegram_id = str(data.get('telegram_id', '')).strip()
        telegram_username = data.get('telegram_username', '')
        ref_code = data.get('ref_code')

        if not telegram_id:
            # If no telegram_id was supplied but user is logged in via web session, use active user
            if request.user.is_authenticated:
                return JsonResponse(build_user_response(request.user))
            return JsonResponse({'error': 'telegram_id is required'}, status=400)

        user = CustomUser.objects.filter(telegram_id=telegram_id).first()
        created = False
        if not user:
            # Create user linked to telegram
            username = telegram_username or f"tg_{telegram_id}"
            base_username = username
            counter = 1
            while CustomUser.objects.filter(username=username).exists():
                username = f"{base_username}_{counter}"
                counter += 1

            email = f"tg_{telegram_id}@live-dev.by"
            user = CustomUser.objects.create(
                username=username,
                email=email,
                telegram_id=telegram_id,
                telegram_username=telegram_username,
                balance=Decimal('15.00'), # 3-day trial balance
                daily_deduction=Decimal('3.50')
            )
            created = True

            if ref_code:
                try:
                    clean_ref = ref_code[4:].strip() if ref_code.startswith('ref_') else ref_code.strip()
                    referrer = CustomUser.objects.get(referral_code=clean_ref)
                    user.referred_by = referrer
                    referrer.balance += Decimal('10.00')
                    referrer.save()
                    user.save()
                except CustomUser.DoesNotExist:
                    pass

        auth_login(request, user)
        response = JsonResponse(build_user_response(user, is_new=created))
        from apps.accounts.views import apply_persistent_auth
        return apply_persistent_auth(request, response, user, remember=True, days=90)
    except Exception as e:
        logger.error(f"Error in tg_sync_view: {e}")
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
def tg_link_account_view(request):
    """
    Called by Telegram Bot when user opens /start link_<code_16>.
    Validates the temporary link code, associates telegram_id,
    and awards +2 free days (+7.00 ₽) if not already claimed.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    try:
        data = json.loads(request.body.decode('utf-8')) if request.body else {}
        code = str(data.get('code', '')).strip()
        telegram_id = str(data.get('telegram_id', '')).strip()
        telegram_username = data.get('telegram_username', '')

        if not code or not telegram_id:
            return JsonResponse({'success': False, 'error': 'Код привязки и telegram_id обязательны'}, status=400)

        link_code = TelegramLinkCode.objects.select_related('user').filter(code=code).first()
        if not link_code or not link_code.is_valid():
            return JsonResponse({'success': False, 'error': 'Неверный или устаревший код привязки. Сгенерируйте новый на сайте.'}, status=400)

        user = link_code.user

        # If this telegram_id is already linked to another user, safely merge if it is a bot shadow account!
        existing = CustomUser.objects.filter(telegram_id=telegram_id).exclude(id=user.id).first()
        if existing:
            is_bot_account = (
                not existing.has_usable_password() or
                existing.email.startswith('tg_') or
                existing.username.startswith('tg_') or
                existing.email.endswith('@live-dev.by')
            )
            if is_bot_account:
                from apps.accounts.services import merge_users
                user = merge_users(target_user=user, source_user=existing)
            else:
                return JsonResponse({
                    'success': False,
                    'error': f'Этот Telegram (@{telegram_username or telegram_id}) уже привязан к основному веб-аккаунту {existing.username}.'
                }, status=400)
        else:
            user.telegram_id = telegram_id
            if telegram_username:
                user.telegram_username = telegram_username

        bonus_awarded = False
        if not user.telegram_bonus_claimed:
            user.balance += Decimal('7.00')  # +2 full days bonus!
            user.telegram_bonus_claimed = True
            bonus_awarded = True

        user.save()
        link_code.delete()  # Consumed

        # Ensure key is synced in 3X-UI
        try:
            user.sync_vpn_access()
        except Exception:
            pass

        return JsonResponse({
            'success': True,
            'bonus_awarded': bonus_awarded,
            'username': user.username,
            'new_balance': float(user.balance),
            'days_left': user.days_left,
            'message': f"Telegram успешно привязан к аккаунту {user.username}!"
        })
    except Exception as e:
        logger.error(f"Error in tg_link_account_view: {e}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
def tg_generate_magic_link_view(request):
    """
    Called by Telegram Bot when user clicks 'Войти в кабинет на ПК'.
    Generates a 15-minute single-use login link.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    try:
        data = json.loads(request.body.decode('utf-8')) if request.body else {}
        telegram_id = str(data.get('telegram_id', '')).strip()

        if not telegram_id:
            return JsonResponse({'success': False, 'error': 'telegram_id is required'}, status=400)

        user = CustomUser.objects.filter(telegram_id=telegram_id).first()
        if not user:
            return JsonResponse({'success': False, 'error': 'Пользователь не найден. Сначала запустите бота.'}, status=404)

        token_obj = MagicLoginToken.create_for_user(user, minutes=15)
        site_url = getattr(settings, 'SITE_URL', 'https://vpn.live-dev.by').rstrip('/')
        login_url = f"{site_url}/auth/magic/{token_obj.token}/"

        return JsonResponse({
            'success': True,
            'login_url': login_url,
            'username': user.username,
        })
    except Exception as e:
        logger.error(f"Error in tg_generate_magic_link_view: {e}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
def toggle_whitelist_api(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    try:
        data = json.loads(request.body.decode('utf-8')) if request.body else {}
        telegram_id = data.get('telegram_id')
        user_id = data.get('user_id')

        user = None
        if telegram_id:
            user = CustomUser.objects.filter(telegram_id=str(telegram_id)).first()
        elif user_id:
            user = CustomUser.objects.filter(id=user_id).first()
        elif request.user.is_authenticated:
            user = request.user

        if not user:
            return JsonResponse({'error': 'User not found'}, status=404)

        key = VPNKey.objects.filter(user=user).first()
        if not key:
            server = get_or_create_default_server()
            key = VPNKey.objects.create(user=user, server=server)

        key.whitelist_enabled = not key.whitelist_enabled
        key.save()

        return JsonResponse({
            'success': True,
            'whitelist_enabled': key.whitelist_enabled,
            'message': 'Белый список РФ обновлен'
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def servers_list_api(request):
    servers = VPNServer.objects.filter(is_active=True).exclude(health_status='blocked_rkn').order_by('order', 'ping_ms')
    return JsonResponse({
        'servers': [
            {
                'id': s.id,
                'name': s.display_name,
                'clean_name': s.clean_name,
                'country_code': s.country_code,
                'country_name': s.country_name,
                'city': s.city,
                'flag': s.flag,
                'ip': s.ip,
                'ping_ms': s.ping_ms,
                'load_percent': s.load_percent,
                'speed_description': s.speed_description,
                'server_type': s.server_type,
                'health_status': s.health_status,
                'is_relay': s.is_relay,
                'is_active': s.is_active,
            }
            for s in servers
        ]
    })


@csrf_exempt
def switch_server_api(request):
    """
    Switch active VPN server for user.
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)
    try:
        data = json.loads(request.body.decode('utf-8')) if request.body else {}
        server_id = data.get('server_id')
        user = None
        if request.user.is_authenticated:
            user = request.user
        elif data.get('telegram_id'):
            user = CustomUser.objects.filter(telegram_id=str(data.get('telegram_id'))).first()
        elif data.get('user_id'):
            user = CustomUser.objects.filter(id=data.get('user_id')).first()

        if not user:
            return JsonResponse({'success': False, 'error': 'User not found'}, status=404)

        server = VPNServer.objects.filter(id=server_id, is_active=True).exclude(health_status='blocked_rkn').first()
        if not server:
            return JsonResponse({'success': False, 'error': 'Сервер недоступен или временно заблокирован'}, status=400)

        key = VPNKey.objects.filter(user=user).first()
        if not key:
            key = VPNKey.objects.create(user=user, server=server)
        else:
            key.server = server
            key.save()

        try:
            user.sync_vpn_access()
        except Exception:
            pass

        res_data = build_user_response(user)
        res_data['success'] = True
        return JsonResponse(res_data)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)





def tariffs_list_api(request):
    plans = TariffPlan.objects.filter(is_active=True)
    packages = SubscriptionPackage.get_active_packages()
    return JsonResponse({
        'plans': [
            {
                'id': p.id,
                'name': p.name,
                'code': p.code,
                'daily_price': float(p.daily_price),
                'speed_mbps': p.speed_mbps,
                'description': p.description,
                'is_featured': p.is_featured,
            }
            for p in plans
        ],
        'packages': [
            {
                'id': pkg.id,
                'name': pkg.name,
                'days': pkg.days,
                'price_rub': float(pkg.price_rub),
                'price_byn': float(pkg.price_byn),
                'daily_rub': float(pkg.daily_rub),
                'badge': pkg.badge,
                'is_featured': pkg.is_featured,
            }
            for pkg in packages
        ]
    })


@csrf_exempt
def buy_traffic_api(request):
    """
    Purchase +50 GB Turbo high-speed quota for 30 ₽.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    user = None
    if request.user.is_authenticated:
        user = request.user
    else:
        data = json.loads(request.body.decode('utf-8')) if request.body else {}
        if data.get('telegram_id'):
            user = CustomUser.objects.filter(telegram_id=str(data.get('telegram_id'))).first()
        elif data.get('user_id'):
            user = CustomUser.objects.filter(id=data.get('user_id')).first()

    if not user:
        return JsonResponse({'error': 'Пользователь не найден'}, status=404)

    price = Decimal('30.00')
    if user.balance < price:
        return JsonResponse({'success': False, 'error': f'Недостаточно средств. Ваш баланс {user.balance} ₽, а требуется 30 ₽.'}, status=400)

    user.balance -= price
    user.save()

    key = VPNKey.objects.filter(user=user).first()
    if not key:
        server = get_or_create_default_server()
        key = VPNKey.objects.create(user=user, server=server)
    key.traffic_limit_gb += 50
    key.is_throttled = False
    key.save()

    return JsonResponse({
        'success': True,
        'message': 'Добавлено +50 ГБ скоростного трафика!',
        **build_user_response(user)
    })


@csrf_exempt
def update_custom_whitelist_api(request):
    """
    Save user's custom domains for direct routing (bypass VPN).
    Accepts JSON: {"domains": "work.corp, provider.by"} or {"telegram_id": ..., "domains": "..."}
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    try:
        data = json.loads(request.body.decode('utf-8')) if request.body else {}
        user = None
        if request.user.is_authenticated:
            user = request.user
        elif data.get('telegram_id'):
            user = CustomUser.objects.filter(telegram_id=str(data.get('telegram_id'))).first()
        elif data.get('user_id'):
            user = CustomUser.objects.filter(id=data.get('user_id')).first()

        if not user:
            return JsonResponse({'error': 'Пользователь не найден'}, status=404)

        key = VPNKey.objects.filter(user=user).first()
        if not key:
            server = get_or_create_default_server()
            key = VPNKey.objects.create(user=user, server=server)

        action = data.get('action')
        if action == 'toggle_ru_by':
            key.whitelist_enabled = not key.whitelist_enabled
            key.save(update_fields=['whitelist_enabled', 'updated_at'])
            msg = 'Обход сайтов РФ и РБ ' + ('ВКЛЮЧЕН' if key.whitelist_enabled else 'ВЫКЛЮЧЕН')
        elif action == 'toggle_zone':
            target_zone = str(data.get('zone', '')).strip().lower().lstrip('.')
            current_zones = key.get_direct_zones()
            if target_zone in current_zones:
                current_zones = [z for z in current_zones if z != target_zone and not (target_zone == 'ru' and z in ('рф', 'xn--p1ai'))]
                msg = f'Зона .{target_zone} исключена из прямого доступа (пойдёт через VPN)'
            else:
                current_zones.append(target_zone)
                msg = f'Зона .{target_zone} возвращена в прямой доступ (мимо VPN)'
            key.direct_zones = ",".join(current_zones)
            key.save(update_fields=['direct_zones', 'updated_at'])
        elif action == 'clear':
            key.custom_whitelist = ""
            key.save(update_fields=['custom_whitelist', 'updated_at'])
            msg = 'Список персональных сайтов очищен'
        elif action == 'clear_proxy':
            key.custom_proxy_list = ""
            key.save(update_fields=['custom_proxy_list', 'updated_at'])
            msg = 'Список сайтов через VPN очищен'
        elif action == 'append':
            raw_new = str(data.get('domain', '')).strip().lower()
            current_domains = key.get_custom_domains()
            for part in raw_new.replace(',', '\n').split('\n'):
                d = part.strip().lstrip('*.')
                if d and d not in current_domains:
                    current_domains.append(d)
            key.custom_whitelist = "\n".join(current_domains)
            key.save(update_fields=['custom_whitelist', 'updated_at'])
            msg = f'Сайт {raw_new} добавлен в прямой доступ (без VPN)!'
        elif action == 'append_proxy':
            raw_new = str(data.get('domain', '')).strip().lower()
            current_proxy = key.get_custom_proxy_domains()
            for part in raw_new.replace(',', '\n').split('\n'):
                d = part.strip().lstrip('*.')
                if d and d not in current_proxy:
                    current_proxy.append(d)
            key.custom_proxy_list = "\n".join(current_proxy)
            key.save(update_fields=['custom_proxy_list', 'updated_at'])
            msg = f'Сайт {raw_new} добавлен в список строго через VPN!'
        else:
            updated_fields = ['updated_at']
            if 'domains' in data:
                key.custom_whitelist = str(data.get('domains', '')).strip()
                updated_fields.append('custom_whitelist')
            if 'proxy_domains' in data:
                key.custom_proxy_list = str(data.get('proxy_domains', '')).strip()
                updated_fields.append('custom_proxy_list')
            if 'direct_zones' in data:
                key.direct_zones = str(data.get('direct_zones', '')).strip()
                updated_fields.append('direct_zones')
            key.save(update_fields=updated_fields)
            msg = 'Настройки маршрутизации сохранены! Нажмите «Обновить» в Incy'

        return JsonResponse({
            'success': True,
            'message': msg,
            'whitelist_enabled': key.whitelist_enabled,
            'custom_whitelist': key.custom_whitelist,
            'custom_domains': key.get_custom_domains(),
            'custom_proxy_list': key.custom_proxy_list,
            'custom_proxy_domains': key.get_custom_proxy_domains(),
            'direct_zones': key.get_direct_zones(),
            **build_user_response(user)
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
def api_deposit_view(request):
    """
    Russian payment / deposit endpoint for Telegram Mini App, Web, and Bot.
    Accepts JSON:
    {
        "telegram_id": ...,
        "amount": 105,
        "payment_method": "sbp" | "mir" | "tpay" | "crypto"
    }
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)
    try:
        data = json.loads(request.body.decode('utf-8')) if request.body else {}
        user = None
        if request.user.is_authenticated:
            user = request.user
        elif data.get('telegram_id'):
            user = CustomUser.objects.filter(telegram_id=str(data.get('telegram_id'))).first()
        elif data.get('user_id'):
            user = CustomUser.objects.filter(id=data.get('user_id')).first()

        if not user:
            return JsonResponse({'success': False, 'error': 'Пользователь не найден'}, status=404)

        amount = Decimal(str(data.get('amount', '105')))
        payment_method = data.get('payment_method', 'sbp')

        if amount < Decimal('10'):
            return JsonResponse({'success': False, 'error': 'Минимальная сумма пополнения — 10 ₽'}, status=400)

        from apps.billing.models import Transaction
        tx = Transaction.objects.create(
            user=user,
            amount=amount,
            payment_method=payment_method,
            status='pending',
            description=f"Пополнение баланса через {payment_method.upper()}"
        )
        tx.complete()
        user.refresh_from_db()

        return JsonResponse({
            'success': True,
            'message': f'Баланс успешно пополнен на {amount} ₽ ({payment_method.upper()})!',
            'transaction_id': tx.id,
            **build_user_response(user)
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


from apps.billing.views import activate_promo_view as activate_promo_api
from apps.billing.views import bepaid_checkout_view as bepaid_checkout_api
from apps.billing.views import yookassa_create_payment_view as yookassa_create_api


@csrf_exempt
def devices_list_api(request):
    """Returns the list of active connected devices for the user."""
    user = None
    if request.user.is_authenticated:
        user = request.user
    elif request.GET.get('telegram_id'):
        user = CustomUser.objects.filter(telegram_id=str(request.GET.get('telegram_id'))).first()
    elif request.GET.get('user_id'):
        user = CustomUser.objects.filter(id=request.GET.get('user_id')).first()

    if not user:
        return JsonResponse({'success': False, 'error': 'User not found'}, status=404)

    from apps.vpn.services import get_user_devices_info
    devices_info = get_user_devices_info(user)
    return JsonResponse({'success': True, 'devices': devices_info})


@csrf_exempt
def reset_devices_api(request):
    """Resets all registered devices and slots for user."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)
    try:
        data = json.loads(request.body.decode('utf-8')) if request.body else {}
        user = None
        if request.user.is_authenticated:
            user = request.user
        elif data.get('telegram_id'):
            user = CustomUser.objects.filter(telegram_id=str(data.get('telegram_id'))).first()
        elif data.get('user_id'):
            user = CustomUser.objects.filter(id=data.get('user_id')).first()

        if not user:
            return JsonResponse({'success': False, 'error': 'User not found'}, status=404)

        from apps.vpn.services import reset_user_devices, get_user_devices_info
        cleared = reset_user_devices(user)
        devices_info = get_user_devices_info(user)
        return JsonResponse({
            'success': True,
            'cleared': cleared,
            'message': f'Все устройства успешно сброшены ({cleared}). Доступно 5 свободных слотов.',
            'devices': devices_info
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
def delete_device_api(request):
    """Deletes a specific registered device for user."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)
    try:
        data = json.loads(request.body.decode('utf-8')) if request.body else {}
        user = None
        if request.user.is_authenticated:
            user = request.user
        elif data.get('telegram_id'):
            user = CustomUser.objects.filter(telegram_id=str(data.get('telegram_id'))).first()
        elif data.get('user_id'):
            user = CustomUser.objects.filter(id=data.get('user_id')).first()

        if not user:
            return JsonResponse({'success': False, 'error': 'User not found'}, status=404)

        device_id = data.get('device_id') or data.get('id')
        if not device_id:
            return JsonResponse({'success': False, 'error': 'device_id is required'}, status=400)

        from apps.vpn.services import delete_user_device, get_user_devices_info
        deleted = delete_user_device(user, device_id)
        devices_info = get_user_devices_info(user)
        return JsonResponse({
            'success': True,
            'deleted': deleted,
            'message': 'Устройство успешно удалено' if deleted else 'Устройство не найдено или уже удалено',
            'devices': devices_info
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)






