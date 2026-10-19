from django.contrib import admin
from .models import TariffPlan, Transaction

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
