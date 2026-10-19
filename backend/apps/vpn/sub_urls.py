from django.urls import path
from . import views

urlpatterns = [
    path('<str:token>/', views.subscription_view, name='subscription'),
]
