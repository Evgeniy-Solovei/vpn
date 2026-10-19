from django.contrib import admin
from .models import VPNServer, VPNKey

@admin.register(VPNServer)
class VPNServerAdmin(admin.ModelAdmin):
    list_display = ('name', 'country_code', 'country_name', 'ip', 'port', 'reality_sni', 'ping_ms', 'is_active', 'created_at')
    list_filter = ('country_code', 'is_active')
    search_fields = ('name', 'ip', 'reality_sni')

@admin.register(VPNKey)
class VPNKeyAdmin(admin.ModelAdmin):
    list_display = ('user', 'server', 'key_uuid', 'whitelist_enabled', 'is_active', 'created_at')
    list_filter = ('whitelist_enabled', 'is_active', 'server')
    search_fields = ('user__username', 'user__email', 'key_uuid', 'sub_token')
