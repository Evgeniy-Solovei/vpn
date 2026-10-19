from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import RedirectView
from django.views.static import serve

def miniapp_serve(request, path=''):
    if not path or path == '/':
        path = 'index.html'
    return serve(request, path, document_root=settings.BASE_DIR.parent / 'miniapp')

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
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
