from django.urls import path
from . import views

urlpatterns = [
    path('pac/<str:token>/', views.pac_view, name='pac_script'),
    path('routing/<str:token>/', views.routing_view, name='incy_routing'),
    path('wg/<str:token>/', views.wireguard_view, name='wireguard_conf'),
    path('wireguard/<str:token>/', views.wireguard_view, name='wireguard_conf_full'),
    path('wg/<str:token>/qr/', views.wireguard_qr_view, name='wireguard_qr'),
    path('qr/<str:token>/', views.qr_code_view, name='qr_code'),
    path('connect/<str:token>/', views.incy_redirect_view, name='incy_connect'),
    path('toggle-whitelist/', views.toggle_whitelist_view, name='toggle_whitelist'),
    path('regenerate-key/', views.regenerate_key_view, name='regenerate_key'),
]
