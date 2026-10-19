from django.contrib import admin
from .models import VPNServer, VPNKey, UserServerTraffic

@admin.register(VPNServer)
class VPNServerAdmin(admin.ModelAdmin):
    list_display = ('name', 'country_code', 'city', 'ip', 'port', 'reality_sni', 'ping_ms', 'load_percent', 'is_active', 'created_at')
    list_filter = ('country_code', 'is_active')
    search_fields = ('name', 'ip', 'city', 'reality_sni')

@admin.register(VPNKey)
class VPNKeyAdmin(admin.ModelAdmin):
    list_display = ('user', 'server', 'used_traffic_gb', 'traffic_limit_gb', 'traffic_percent', 'is_throttled', 'traffic_reset_date', 'whitelist_enabled', 'is_active')
    list_filter = ('is_throttled', 'whitelist_enabled', 'is_active', 'server')
    search_fields = ('user__username', 'user__email', 'key_uuid', 'sub_token')
    actions = ['reset_traffic_action']

    def reset_traffic_action(self, request, queryset):
        for key in queryset:
            key.reset_monthly_traffic()
        self.message_user(request, f"Сброшен трафик для {queryset.count()} ключей.")
    reset_traffic_action.short_description = "Сбросить месячный трафик выбранных ключей"

@admin.register(UserServerTraffic)
class UserServerTrafficAdmin(admin.ModelAdmin):
    list_display = ('user', 'server', 'used_gb', 'updated_at')
    list_filter = ('server',)
    search_fields = ('user__username', 'server__name')
