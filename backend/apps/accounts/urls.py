from django.urls import path
from . import views

urlpatterns = [
    path('register/', views.register_view, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('password-reset/', views.password_reset_request_view, name='password_reset'),
    path('password-reset/done/', views.password_reset_done_view, name='password_reset_done'),
    path('password-reset-confirm/<uidb64>/<token>/', views.password_reset_confirm_view, name='password_reset_confirm'),
    path('telegram-link-code/', views.generate_telegram_link_code_view, name='telegram_link_code'),
    path('telegram-callback/', views.telegram_auth_callback_view, name='telegram_auth_callback'),
    path('magic/<str:token>/', views.magic_login_view, name='magic_login'),
]
