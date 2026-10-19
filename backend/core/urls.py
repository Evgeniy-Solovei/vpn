from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import RedirectView
from django.views.static import serve as static_serve
from django.contrib.staticfiles.views import serve as staticfiles_serve

def robust_static_serve(request, path):
    try:
        return staticfiles_serve(request, path, insecure=True)
    except Exception:
        return static_serve(request, path, document_root=settings.STATIC_ROOT)

def miniapp_serve(request, path=''):
    if not path or path == '/':
        path = 'index.html'
    return static_serve(request, path, document_root=settings.BASE_DIR.parent / 'miniapp')

urlpatterns = [
    path('admin/', admin.site.urls),
    path('auth/', include('apps.accounts.urls')),
    path('dashboard/', include('apps.accounts.dashboard_urls')),
    path('billing/', include('apps.billing.urls')),
    path('vpn/', include('apps.vpn.urls')),
    path('sub/', include('apps.vpn.sub_urls')),
    path('api/', include('apps.api.urls')),
    re_path(r'^miniapp/(?P<path>.*)$', miniapp_serve, name='miniapp'),
    path('', RedirectView.as_view(url='/dashboard/', permanent=False)),
    re_path(r'^static/(?P<path>.*)$', robust_static_serve, name='static_files'),
    re_path(r'^media/(?P<path>.*)$', static_serve, {'document_root': settings.MEDIA_ROOT}, name='media_files'),
]

