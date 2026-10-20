from django.contrib import admin
from .models import TariffPlan, Transaction, PromoCode, PaymentOrder, YooKassaOrder

@admin.register(TariffPlan)
class TariffPlanAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'daily_price', 'speed_mbps', 'is_featured', 'is_active')
    list_editable = ('daily_price', 'speed_mbps', 'is_active')

@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'amount', 'payment_method', 'status', 'created_at')
    list_filter = ('status', 'payment_method', 'created_at')
    search_fields = ('user__username', 'user__email', 'external_id')
    actions = ['mark_as_completed']

    @admin.action(description="Пометить выбранные как Оплачено и зачислить баланс")
    def mark_as_completed(self, request, queryset):
        for tx in queryset:
            tx.complete()

@admin.register(PromoCode)
class PromoCodeAdmin(admin.ModelAdmin):
    list_display = ('code', 'days', 'used_count', 'max_uses', 'is_active', 'created_at')
    list_filter = ('is_active', 'days')
    search_fields = ('code',)

@admin.register(PaymentOrder)
class PaymentOrderAdmin(admin.ModelAdmin):
    list_display = ('order_id', 'user', 'amount_byn', 'amount_rub', 'days', 'status', 'created_at', 'paid_at')
    list_filter = ('status', 'created_at')
    search_fields = ('order_id', 'user__username', 'user__email', 'bepaid_token')
    actions = ['mark_order_paid']

    @admin.action(description="Активировать заказ вручную (Оплачен)")
    def mark_order_paid(self, request, queryset):
        for order in queryset:
            order.complete_payment()


@admin.register(YooKassaOrder)
class YooKassaOrderAdmin(admin.ModelAdmin):
    list_display = ('order_id', 'payment_id', 'user', 'amount_rub', 'days', 'payment_method_type', 'status', 'created_at', 'paid_at')
    list_filter = ('status', 'payment_method_type', 'created_at')
    search_fields = ('order_id', 'payment_id', 'user__username', 'user__email')
    actions = ['mark_order_paid']

    @admin.action(description="Активировать заказ ЮKassa вручную (Оплачен)")
    def mark_order_paid(self, request, queryset):
        for order in queryset:
            order.complete_payment()

