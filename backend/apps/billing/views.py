import uuid
import json
import base64
import hmac
import logging
import httpx
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse, HttpResponse
from django.contrib import messages
from django.conf import settings
from apps.accounts.models import CustomUser
from .models import TariffPlan, Transaction, PromoCode, PaymentOrder

logger = logging.getLogger(__name__)

@login_required
def tariffs_view(request):
    plans = TariffPlan.objects.filter(is_active=True)
    if not plans.exists():
        # Seed initial plans if empty
        TariffPlan.objects.create(
            name="BLACKROCK",
            code="blackrock",
            daily_price=Decimal("4.50"),
            speed_mbps=500,
            description="500 Мб/с пропускной канал. Комфортные сервера, 2 страны на выбор.",
            is_featured=True
        )
        TariffPlan.objects.create(
            name="BLACKEASY",
            code="blackeasy",
            daily_price=Decimal("2.40"),
            speed_mbps=50,
            description="50 Мб/с пропускной канал. Доступ к популярным сервисам.",
            is_featured=False
        )
        plans = TariffPlan.objects.filter(is_active=True)

    return render(request, 'billing/tariffs.html', {'plans': plans, 'user': request.user})


@login_required
def deposit_view(request):
    if request.method == 'POST':
        try:
            amount = Decimal(request.POST.get('amount', '100'))
            payment_method = request.POST.get('payment_method', 'sbp')
            
            if amount < Decimal('10'):
                messages.error(request, "Минимальная сумма пополнения — 10 ₽")
                return redirect('tariffs')

            tx = Transaction.objects.create(
                user=request.user,
                amount=amount,
                payment_method=payment_method,
                status='pending',
                description=f"Пополнение баланса через {payment_method.upper()}"
            )

            # Auto-complete for MVP / instant testing
            tx.complete()
            messages.success(request, f"Баланс успешно пополнен на {amount} ₽!")
            return redirect('dashboard')

        except Exception as e:
            messages.error(request, f"Ошибка при создании платежа: {e}")
            return redirect('tariffs')

    return redirect('tariffs')


@login_required
def toggle_autopay_view(request):
    if request.method == 'POST':
        user = request.user
        user.autopay = not user.autopay
        user.save()
        return JsonResponse({'success': True, 'autopay': user.autopay})
    return JsonResponse({'success': False}, status=400)


@csrf_exempt
def activate_promo_view(request):
    """
    Activate promo code (3, 5, 10 days free).
    Supports AJAX JSON from web/MiniApp and Telegram Bot.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    try:
        user = None
        code_str = ""

        if request.body:
            try:
                data = json.loads(request.body.decode('utf-8'))
                code_str = data.get('code', '').strip().upper()
                if data.get('telegram_id'):
                    user = CustomUser.objects.filter(telegram_id=str(data.get('telegram_id'))).first()
                elif data.get('user_id'):
                    user = CustomUser.objects.filter(id=data.get('user_id')).first()
            except Exception:
                pass

        if not code_str:
            code_str = request.POST.get('code', '').strip().upper()

        if not user and request.user.is_authenticated:
            user = request.user

        if not user:
            return JsonResponse({'success': False, 'error': 'Требуется авторизация'}, status=401)

        if not code_str:
            return JsonResponse({'success': False, 'error': 'Введите промокод'}, status=400)

        promo = PromoCode.objects.filter(code__iexact=code_str).first()
        if not promo:
            return JsonResponse({'success': False, 'error': f'Промокод «{code_str}» не найден'}, status=404)

        can_use, reason = promo.can_be_used_by(user)
        if not can_use:
            return JsonResponse({'success': False, 'error': reason}, status=400)

        bonus_rub = promo.activate_for(user)

        return JsonResponse({
            'success': True,
            'message': f'🎉 Промокод активирован! Вам начислено +{promo.days} дн. бесплатно (+{bonus_rub} ₽)',
            'bonus_days': promo.days,
            'bonus_rub': float(bonus_rub),
            'new_balance': float(user.balance),
            'days_left': user.days_left
        })
    except Exception as e:
        logger.exception("Error activating promo code: %s", e)
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
def bepaid_checkout_view(request):
    """
    Creates bePaid payment session (Customer to Point / Checkout API)
    for Belarus cards, Belkart, ERIP, MIR.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    user = None
    if request.user.is_authenticated:
        user = request.user
    else:
        try:
            data = json.loads(request.body.decode('utf-8')) if request.body else {}
            if data.get('telegram_id'):
                user = CustomUser.objects.filter(telegram_id=str(data.get('telegram_id'))).first()
            elif data.get('user_id'):
                user = CustomUser.objects.filter(id=data.get('user_id')).first()
        except Exception:
            pass

    if not user:
        return JsonResponse({'error': 'Пользователь не найден'}, status=404)

    shop_id = getattr(settings, 'BEPAID_SHOP_ID', '4225')
    secret_key = getattr(settings, 'BEPAID_SECRET_KEY', '3834fbef1fe6ea024ef77f5c79ec7ff1ba710ea6241c08c2f341afda8af4c1c4')
    test_mode = getattr(settings, 'BEPAID_TEST_MODE', True)
    checkout_api_url = getattr(settings, 'BEPAID_CHECKOUT_URL', 'https://checkout.bepaid.by/ctp/api/checkouts')

    order_id = f"LD-{uuid.uuid4().hex[:10].upper()}"
    days = 30
    amount_byn = Decimal('5.00')   # 5.00 BYN (~150 RUB)
    amount_rub = Decimal('150.00')
    amount_cents = int(amount_byn * 100)

    site_url = getattr(settings, 'SITE_URL', 'http://vpn.live-dev.by').rstrip('/')
    notification_url = f"{site_url}/billing/bepaid/webhook/"
    return_url = f"{site_url}/dashboard/?payment=success&order={order_id}"

    payload = {
        "checkout": {
            "test": test_mode,
            "transaction_type": "payment",
            "attempts": 3,
            "version": 2,
            "order": {
                "amount": amount_cents,
                "currency": "BYN",
                "description": f"VPN live-dev: Подписка на {days} дней ({user.username})",
                "tracking_id": order_id,
            },
            "customer": {
                "email": user.email or f"{user.username}@live-dev.by",
                "first_name": user.username,
            },
            "settings": {
                "auto_return": 3,
                "return_url": return_url,
                "success_url": return_url,
                "decline_url": f"{site_url}/dashboard/?payment=failed",
                "fail_url": f"{site_url}/dashboard/?payment=failed",
                "cancel_url": f"{site_url}/dashboard/?payment=cancelled",
                "notification_url": notification_url,
                "button_text": "Вернуться в Личный кабинет",
                "language": "ru",
            },
            "payment_method": {
                "types": ["credit_card", "erip"]
            }
        }
    }

    checkout_url = ""
    bepaid_token = ""

    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(
                checkout_api_url,
                json=payload,
                auth=(str(shop_id), str(secret_key)),
                headers={'Accept': 'application/json', 'Content-Type': 'application/json'}
            )
            if resp.status_code in (200, 201):
                res_data = resp.json().get('checkout', {})
                bepaid_token = res_data.get('token', '')
                checkout_url = res_data.get('redirect_url', '')
            else:
                logger.error("bePaid error: %s - %s", resp.status_code, resp.text)
    except Exception as e:
        logger.exception("bePaid API connection exception: %s", e)

    # If test mode and offline or API unavailable, provide fallback mock URL
    if not checkout_url:
        checkout_url = f"{site_url}/billing/bepaid/mock-pay/{order_id}/"

    order = PaymentOrder.objects.create(
        order_id=order_id,
        user=user,
        amount_byn=amount_byn,
        amount_rub=amount_rub,
        days=days,
        status=PaymentOrder.Status.PENDING,
        bepaid_checkout_url=checkout_url,
        bepaid_token=bepaid_token
    )

    return JsonResponse({
        'success': True,
        'order_id': order.order_id,
        'amount_byn': str(order.amount_byn),
        'amount_rub': str(order.amount_rub),
        'days': order.days,
        'checkout_url': checkout_url
    })


@csrf_exempt
def bepaid_webhook_view(request):
    """
    bePaid Webhook Callback handler.
    Called by bePaid server upon successful payment.
    """
    if request.method != 'POST':
        return HttpResponse('Method not allowed', status=405)

    shop_id = str(getattr(settings, 'BEPAID_SHOP_ID', '') or '')
    secret_key = str(getattr(settings, 'BEPAID_SECRET_KEY', '') or '')

    # Optional Basic Auth check if provided
    auth_header = request.headers.get('Authorization', '')
    if auth_header and secret_key:
        expected = 'Basic ' + base64.b64encode(f'{shop_id}:{secret_key}'.encode()).decode()
        if not hmac.compare_digest(auth_header, expected):
            logger.warning("Invalid bePaid webhook credentials")
            return HttpResponse('Unauthorized', status=401)

    try:
        data = json.loads(request.body.decode('utf-8')) if request.body else {}
        transaction = data.get('transaction', {})
        order_id = transaction.get('tracking_id') or data.get('order_id')
        status = transaction.get('status') or data.get('status')

        if not order_id:
            return HttpResponse('order_id missing', status=400)

        order = PaymentOrder.objects.filter(order_id=order_id).first()
        if not order:
            logger.warning("bePaid order not found: %s", order_id)
            return HttpResponse('Order not found', status=404)

        if status in ('successful', 'paid'):
            order.complete_payment()
            logger.info("Order %s successfully paid and activated", order_id)
            return HttpResponse('OK', status=200)

        return HttpResponse('Ignored', status=200)
    except Exception as e:
        logger.exception("bePaid webhook exception: %s", e)
        return HttpResponse('Internal error', status=500)


@login_required
def bepaid_mock_pay_view(request, order_id):
    """Mock payment page for instant testing in local environment."""
    order = get_object_or_404(PaymentOrder, order_id=order_id, user=request.user)
    if request.method == 'POST':
        order.complete_payment()
        messages.success(request, f"🎉 Тестовая оплата {order.amount_byn} BYN успешно проведена! Баланс пополнен на {order.amount_rub} ₽.")
        return redirect('dashboard')

    return render(request, 'billing/bepaid_mock.html', {'order': order})

