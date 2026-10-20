from django.contrib import admin
from .models import VPNServer, VPNKey, UserServerTraffic
from .services import check_server_health, failover_banned_servers

@admin.register(VPNServer)
class VPNServerAdmin(admin.ModelAdmin):
    list_display = ('name', 'country_code', 'server_type', 'health_status', 'ip', 'port', 'ping_ms', 'load_percent', 'is_active', 'last_checked_at')
    list_filter = ('server_type', 'health_status', 'is_active', 'country_code')
    search_fields = ('name', 'ip', 'city', 'reality_sni', 'country_name')
    actions = ['check_health_action', 'hide_server_action', 'activate_server_action', 'mark_rkn_blocked_action']

    def check_health_action(self, request, queryset):
        for server in queryset:
            check_server_health(server)
        self.message_user(request, f"Проверена доступность {queryset.count()} серверов.")
    check_health_action.short_description = "🔍 Проверить пинг и статус выбранных серверов"

    def hide_server_action(self, request, queryset):
        queryset.update(is_active=False)
        migrated = failover_banned_servers()
        self.message_user(request, f"Скрыто {queryset.count()} серверов. Переведено пользователей на резервные: {migrated}.")
    hide_server_action.short_description = "👁️ Скрыть выбранные сервера (is_active=False) и перевести пользователей"

    def activate_server_action(self, request, queryset):
        queryset.update(is_active=True, health_status='online')
        self.message_user(request, f"Активировано {queryset.count()} серверов.")
    activate_server_action.short_description = "✅ Активировать выбранные сервера"

    def mark_rkn_blocked_action(self, request, queryset):
        for s in queryset:
            s.mark_blocked_rkn(reason="Ручная блокировка через панель администратора")
        migrated = failover_banned_servers()
        self.message_user(request, f"Помечено как заблокированные РКН: {queryset.count()} серверов. Авто-переведено пользователей: {migrated}.")
    mark_rkn_blocked_action.short_description = "🔴 Пометить как заблокированные РКН и спасти пользователей (Auto-Failover)"


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
