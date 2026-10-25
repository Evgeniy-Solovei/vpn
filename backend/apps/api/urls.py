from django.urls import path
from . import views

urlpatterns = [
    path('user/profile/', views.user_profile_api, name='api_user_profile'),
    path('auth/demo-login/', views.demo_login_api, name='api_demo_login'),
    path('tg/sync/', views.tg_sync_view, name='api_tg_sync'),
    path('tg/link-account/', views.tg_link_account_view, name='api_tg_link_account'),
    path('tg/generate-magic-link/', views.tg_generate_magic_link_view, name='api_tg_generate_magic_link'),
    path('vpn/toggle-whitelist/', views.toggle_whitelist_api, name='api_toggle_whitelist'),
    path('vpn/servers/', views.servers_list_api, name='api_servers_list'),
    path('vpn/switch-server/', views.switch_server_api, name='api_switch_server'),
    path('vpn/devices/', views.devices_list_api, name='api_devices_list'),
    path('vpn/devices/reset/', views.reset_devices_api, name='api_devices_reset'),
    path('vpn/devices/delete/', views.delete_device_api, name='api_devices_delete'),
    path('vpn/buy-traffic/', views.buy_traffic_api, name='api_buy_traffic'),
    path('vpn/custom-whitelist/', views.update_custom_whitelist_api, name='api_custom_whitelist'),
    path('billing/tariffs/', views.tariffs_list_api, name='api_tariffs_list'),
    path('billing/deposit/', views.api_deposit_view, name='api_deposit'),
    path('billing/activate-promo/', views.activate_promo_api, name='api_activate_promo'),
    path('billing/bepaid/checkout/', views.bepaid_checkout_api, name='api_bepaid_checkout'),
    path('billing/yookassa/create/', views.yookassa_create_api, name='api_yookassa_create'),
]

