from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.contrib import messages
from .models import TariffPlan, Transaction

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
