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
from .models import TariffPlan, Transaction, PromoCode, PaymentOrder, YooKassaOrder

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


@csrf_exempt
def yookassa_create_payment_view(request):
    """
    Creates YooKassa payment session (API v3) for Russia.
    Supports SBP, MIR Cards, SberPay, T-Pay, and YooMoney.
    Fully compatible with self-employed taxation (НПД).
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
        if request.headers.get('Accept') == 'application/json' or request.content_type == 'application/json':
            return JsonResponse({'error': 'Пользователь не найден'}, status=404)
        messages.error(request, "Для пополнения необходимо авторизоваться")
        return redirect('login')

    # Read params from POST form or JSON
    amount_str = '105'
    payment_method = 'sbp'
    if request.content_type == 'application/json' and request.body:
        try:
            payload_data = json.loads(request.body.decode('utf-8'))
            amount_str = str(payload_data.get('amount', '105'))
            payment_method = payload_data.get('payment_method', 'sbp')
        except Exception:
            pass
    else:
        amount_str = request.POST.get('amount', '105')
        payment_method = request.POST.get('payment_method', 'sbp')

    try:
        amount_rub = Decimal(amount_str)
        if amount_rub < Decimal('10'):
            amount_rub = Decimal('10')
    except Exception:
        amount_rub = Decimal('105.00')

    daily_price = user.daily_deduction or Decimal('3.50')
    days = max(1, int(amount_rub / daily_price))

    order_id = f"LD-YK-{uuid.uuid4().hex[:10].upper()}"
    shop_id = getattr(settings, 'YOOKASSA_SHOP_ID', '')
    secret_key = getattr(settings, 'YOOKASSA_SECRET_KEY', '')
    api_url = getattr(settings, 'YOOKASSA_API_URL', 'https://api.yookassa.ru/v3/payments')
    site_url = getattr(settings, 'SITE_URL', 'https://vpn.live-dev.by').rstrip('/')
    return_url = f"{site_url}/dashboard/?payment=yookassa_success&order={order_id}"

    payment_id = ""
    confirmation_url = ""

    if shop_id and secret_key:
        idempotence_key = str(uuid.uuid4())
        user_email = user.email or (f"user_{user.telegram_id}@live-dev.by" if user.telegram_id else f"{user.username}@live-dev.by")
        yoo_payload = {
            "amount": {
                "value": f"{amount_rub:.2f}",
                "currency": "RUB"
            },
            "capture": True,
            "confirmation": {
                "type": "redirect",
                "return_url": return_url
            },
            "description": f"VPN live-dev: Подписка {days} дн. ({user.username})"[:128],
            "metadata": {
                "order_id": order_id,
                "user_id": str(user.id),
                "username": user.username,
                "telegram_id": str(user.telegram_id or ""),
                "days": str(days)
            },
            "receipt": {
                "customer": {
                    "email": user_email
                },
                "items": [
                    {
                        "description": f"VPN live-dev: Подписка {days} дн."[:128],
                        "quantity": "1.00",
                        "amount": {
                            "value": f"{amount_rub:.2f}",
                            "currency": "RUB"
                        },
                        "vat_code": 4,  # 4 = Без НДС (для самозанятых / УСН без НДС)
                        "payment_mode": "full_payment",
                        "payment_subject": "service"
                    }
                ]
            }
        }

        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.post(
                    api_url,
                    json=yoo_payload,
                    auth=(str(shop_id), str(secret_key)),
                    headers={
                        'Idempotence-Key': idempotence_key,
                        'Content-Type': 'application/json',
                        'Accept': 'application/json'
                    }
                )
                if resp.status_code in (200, 201):
                    res_json = resp.json()
                    payment_id = res_json.get('id', '')
                    confirmation_url = res_json.get('confirmation', {}).get('confirmation_url', '')
                else:
                    logger.error("YooKassa API error %s: %s", resp.status_code, resp.text)
        except Exception as e:
            logger.exception("YooKassa API connection exception: %s", e)

    # If mock/sandbox or offline fallback
    if not confirmation_url:
        confirmation_url = f"{site_url}/billing/yookassa/mock-pay/{order_id}/"

    order = YooKassaOrder.objects.create(
        order_id=order_id,
        payment_id=payment_id,
        user=user,
        amount_rub=amount_rub,
        days=days,
        payment_method_type=payment_method,
        status=YooKassaOrder.Status.PENDING,
        confirmation_url=confirmation_url
    )

    is_json = (
        request.headers.get('Accept') == 'application/json' or
        request.content_type == 'application/json' or
        request.headers.get('X-Requested-With') == 'XMLHttpRequest' or
        request.POST.get('format') == 'json'
    )
    if is_json:
        return JsonResponse({
            'success': True,
            'order_id': order.order_id,
            'payment_id': order.payment_id,
            'amount_rub': f"{order.amount_rub:.2f}",
            'days': order.days,
            'checkout_url': confirmation_url,
            'confirmation_url': confirmation_url
        })

    return redirect(confirmation_url)


@csrf_exempt
def yookassa_webhook_view(request):
    """
    YooKassa Webhook Callback handler (API v3).
    Receives notification: payment.succeeded / payment.canceled.
    """
    if request.method != 'POST':
        return HttpResponse('Method not allowed', status=405)

    try:
        data = json.loads(request.body.decode('utf-8')) if request.body else {}
        event = data.get('event')
        obj = data.get('object', {})
        payment_id = obj.get('id')
        metadata = obj.get('metadata', {})
        order_id = metadata.get('order_id')
        status = obj.get('status')

        order = None
        if payment_id:
            order = YooKassaOrder.objects.filter(payment_id=payment_id).first()
        if not order and order_id:
            order = YooKassaOrder.objects.filter(order_id=order_id).first()

        if not order:
            logger.warning("YooKassa order not found for payment_id=%s, order_id=%s", payment_id, order_id)
            return HttpResponse('Order not found', status=404)

        if event == 'payment.succeeded' or status == 'succeeded':
            order.complete_payment()
            logger.info("YooKassa order %s (%s ₽) successfully marked paid", order.order_id, order.amount_rub)
            return HttpResponse('OK', status=200)

        elif event == 'payment.canceled' or status == 'canceled':
            order.status = YooKassaOrder.Status.CANCELED
            order.save(update_fields=['status'])
            logger.info("YooKassa order %s canceled", order.order_id)
            return HttpResponse('OK', status=200)

        return HttpResponse('OK', status=200)
    except Exception as e:
        logger.exception("YooKassa webhook exception: %s", e)
        return HttpResponse('Internal error', status=500)


@login_required
def yookassa_mock_pay_view(request, order_id):
    """
    Simulated YooKassa payment checkout for local dev & testing.
    Presents SBP QR-code & Russian Bank Card options, matching official YooKassa styling.
    """
    order = get_object_or_404(YooKassaOrder, order_id=order_id, user=request.user)
    if request.method == 'POST':
        order.complete_payment()
        messages.success(request, f"🎉 Оплата {order.amount_rub} ₽ через ЮKassa успешно подтверждена! Добавлено +{order.days} дней доступа.")
        return redirect('dashboard')

    return render(request, 'billing/yookassa_mock.html', {'order': order})


