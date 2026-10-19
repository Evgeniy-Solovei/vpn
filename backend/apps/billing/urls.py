from django.urls import path
from . import views

urlpatterns = [
    path('tariffs/', views.tariffs_view, name='tariffs'),
    path('deposit/', views.deposit_view, name='deposit'),
    path('toggle-autopay/', views.toggle_autopay_view, name='toggle_autopay'),
]
