from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import RedirectView
from django.views.static import serve as static_serve
from django.contrib.staticfiles.views import serve as staticfiles_serve
from apps.billing import views as billing_views
from apps.accounts import views as accounts_views

def robust_static_serve(request, path):
    try:
        return staticfiles_serve(request, path, insecure=True)
    except Exception:
        return static_serve(request, path, document_root=settings.STATIC_ROOT)

def miniapp_serve(request, path=''):
    if not path or path == '/':
        path = 'index.html'
    return static_serve(request, path, document_root=settings.BASE_DIR.parent / 'miniapp')

admin_path = getattr(settings, 'ADMIN_URL_PATH', 'management-hq').strip('/')

# Strict superuser enforcement: only active superusers can access admin panel
admin.site.has_permission = lambda request: bool(request.user.is_active and request.user.is_superuser)
admin.site.site_header = "VPN live-dev | Панель управления"
admin.site.site_title = "VPN live-dev Admin"

urlpatterns = [
    # Standard /admin/ is deliberately disabled and returns 404 for security
    path('admin/', accounts_views.custom_404_handler),
    path(f'{admin_path}/', admin.site.urls),
    path('auth/', include('apps.accounts.urls')),
    path('dashboard/', include('apps.accounts.dashboard_urls')),
    path('billing/', include('apps.billing.urls')),
    path('tariffs/', billing_views.tariffs_view, name='root_tariffs'),
    path('legal/', billing_views.legal_view, name='root_legal'),
    path('requisites/', billing_views.legal_view, name='root_requisites'),
    path('terms/', billing_views.legal_view, name='root_terms'),
    path('vpn/', include('apps.vpn.urls')),
    path('sub/', include('apps.vpn.sub_urls')),
    path('api/', include('apps.api.urls')),
    re_path(r'^miniapp/(?P<path>.*)$', RedirectView.as_view(url='/dashboard/', permanent=False), name='miniapp'),
    path('', RedirectView.as_view(url='/dashboard/', permanent=False)),
    re_path(r'^static/(?P<path>.*)$', robust_static_serve, name='static_files'),
    re_path(r'^media/(?P<path>.*)$', static_serve, {'document_root': settings.MEDIA_ROOT}, name='media_files'),
]

handler500 = 'apps.accounts.views.custom_500_handler'
handler404 = 'apps.accounts.views.custom_404_handler'


