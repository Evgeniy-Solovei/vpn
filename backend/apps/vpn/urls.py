from django.urls import path
from . import views

urlpatterns = [
    path('pac/<str:token>/', views.pac_view, name='pac_script'),
    path('qr/<str:token>/', views.qr_code_view, name='qr_code'),
    path('toggle-whitelist/', views.toggle_whitelist_view, name='toggle_whitelist'),
    path('regenerate-key/', views.regenerate_key_view, name='regenerate_key'),
]
