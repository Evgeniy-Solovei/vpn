from django.urls import path, re_path
from . import views

urlpatterns = [
    re_path(r'^pac/(?P<token>[^/]+)/?$', views.pac_view, name='pac_script'),
    re_path(r'^routing/(?P<token>[^/]+)/?$', views.routing_view, name='incy_routing'),
    re_path(r'^wg/(?P<token>[^/]+)/?$', views.wireguard_view, name='wireguard_conf'),
    re_path(r'^wireguard/(?P<token>[^/]+)/?$', views.wireguard_view, name='wireguard_conf_full'),
    re_path(r'^wg/(?P<token>[^/]+)/qr/?$', views.wireguard_qr_view, name='wireguard_qr'),
    re_path(r'^qr/(?P<token>[^/]+)/?$', views.qr_code_view, name='qr_code'),
    re_path(r'^connect/(?P<token>[^/]+)/?$', views.incy_redirect_view, name='incy_connect'),
    path('toggle-whitelist/', views.toggle_whitelist_view, name='toggle_whitelist'),
    path('regenerate-key/', views.regenerate_key_view, name='regenerate_key'),
]
