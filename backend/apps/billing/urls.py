from django.urls import path
from . import views

urlpatterns = [
    path('tariffs/', views.tariffs_view, name='tariffs'),
    path('deposit/', views.deposit_view, name='deposit'),
    path('toggle-autopay/', views.toggle_autopay_view, name='toggle_autopay'),
    path('promo/activate/', views.activate_promo_view, name='billing_activate_promo'),
    path('bepaid/checkout/', views.bepaid_checkout_view, name='bepaid_checkout'),
    path('bepaid/webhook/', views.bepaid_webhook_view, name='bepaid_webhook'),
    path('bepaid/mock-pay/<str:order_id>/', views.bepaid_mock_pay_view, name='bepaid_mock_pay'),
]
