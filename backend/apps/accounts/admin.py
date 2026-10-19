from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser

@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    list_display = ('username', 'email', 'balance', 'daily_deduction', 'days_left', 'autopay', 'telegram_id', 'referral_code', 'created_at')
    list_filter = ('autopay', 'is_staff', 'is_superuser', 'created_at')
    search_fields = ('username', 'email', 'telegram_id', 'referral_code')
    ordering = ('-created_at',)
    
    fieldsets = UserAdmin.fieldsets + (
        ('VPN & Биллинг', {
            'fields': ('balance', 'daily_deduction', 'autopay', 'telegram_id', 'telegram_username', 'referral_code', 'referred_by')
        }),
    )
