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


from .models import DeviceAuthKey, ErrorIncident

@admin.register(DeviceAuthKey)
class DeviceAuthKeyAdmin(admin.ModelAdmin):
    list_display = ('user', 'key', 'ip_address', 'created_at', 'expires_at', 'is_valid')
    search_fields = ('user__username', 'user__email', 'key', 'ip_address')
    list_filter = ('created_at', 'expires_at')
    readonly_fields = ('created_at',)


@admin.register(ErrorIncident)
class ErrorIncidentAdmin(admin.ModelAdmin):
    list_display = ('incident_id', 'error_message', 'path', 'method', 'user', 'created_at', 'is_resolved')
    list_filter = ('is_resolved', 'method', 'created_at')
    search_fields = ('incident_id', 'error_message', 'path', 'user__username', 'ip_address')
    readonly_fields = ('incident_id', 'error_message', 'traceback', 'path', 'method', 'user', 'ip_address', 'user_agent', 'created_at')


