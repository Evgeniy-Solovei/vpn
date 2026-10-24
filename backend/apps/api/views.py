import json
import logging
from decimal import Decimal
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from django.contrib.auth import login as auth_login
from apps.accounts.models import CustomUser
from apps.vpn.models import VPNServer, VPNKey
from apps.vpn.services import get_or_create_default_server
from apps.billing.models import TariffPlan, Transaction

logger = logging.getLogger(__name__)


def build_user_response(user, is_new=False):
    key = VPNKey.objects.filter(user=user).first()
    if not key:
        server = get_or_create_default_server()
        key, _ = VPNKey.objects.get_or_create(user=user, server=server)
    else:
        server = key.server

    site_url = getattr(settings, 'SITE_URL', 'http://vpn.live-dev.by')
    referral_url = f"{site_url}/auth/register/?ref={user.referral_code}"

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
            'referrals_count': user.referrals.count(),
        },
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
            'vless_url': key.get_vless_url(),
            'sub_url': key.get_sub_url(),
            'incy_url': key.get_incy_url(),
            'connect_url': key.get_connect_url(),
            'whitelist_enabled': key.whitelist_enabled,
            'custom_whitelist': key.custom_whitelist,
            'custom_domains': key.get_custom_domains(),
            'qr_url': f"{site_url}/vpn/qr/{key.sub_token}/",
            'pac_url': f"{site_url}/vpn/pac/{key.sub_token}/",
        },
        'traffic': {
            'used_gb': key.used_traffic_gb,
            'limit_gb': key.traffic_limit_gb,
            'is_unlimited': getattr(key, 'is_unlimited', True),
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
                    referrer = CustomUser.objects.get(referral_code=ref_code)
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

        res_data = build_user_response(user)
        res_data['success'] = True
        return JsonResponse(res_data)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)





def tariffs_list_api(request):
    plans = TariffPlan.objects.filter(is_active=True)
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

        domains_text = data.get('domains', '')
        key.custom_whitelist = domains_text.strip()
        key.save(update_fields=['custom_whitelist', 'updated_at'])

        return JsonResponse({
            'success': True,
            'message': 'Список сайтов-исключений сохранен!',
            'custom_domains': key.get_custom_domains(),
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




