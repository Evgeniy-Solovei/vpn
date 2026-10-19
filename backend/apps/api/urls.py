from django.urls import path
from . import views

urlpatterns = [
    path('tg/sync/', views.tg_sync_view, name='api_tg_sync'),
    path('vpn/toggle-whitelist/', views.toggle_whitelist_api, name='api_toggle_whitelist'),
    path('vpn/servers/', views.servers_list_api, name='api_servers_list'),
    path('billing/tariffs/', views.tariffs_list_api, name='api_tariffs_list'),
]
