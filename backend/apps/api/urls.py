from django.urls import path
from . import views

urlpatterns = [
    path('user/profile/', views.user_profile_api, name='api_user_profile'),
    path('auth/demo-login/', views.demo_login_api, name='api_demo_login'),
    path('tg/sync/', views.tg_sync_view, name='api_tg_sync'),
    path('vpn/toggle-whitelist/', views.toggle_whitelist_api, name='api_toggle_whitelist'),
    path('vpn/servers/', views.servers_list_api, name='api_servers_list'),
    path('billing/tariffs/', views.tariffs_list_api, name='api_tariffs_list'),
]

