from django.contrib import admin
from django.urls import path, include, re_path
from django.contrib.staticfiles.views import serve as static_serve
from django.http import HttpResponse
from django.contrib.staticfiles import finders

def diag_static(request):
    """诊断：检查 staticfiles 是否能找到文件"""
    from django.conf import settings
    lines = [
        f"STATIC_URL: {settings.STATIC_URL}",
        f"DEBUG: {settings.DEBUG}",
    ]
    for p in ['admin/css/base.css', 'admin/js/theme.js', 'admin/css/login.css']:
        found = finders.find(p)
        lines.append(f"finders.find('{p}'): {found}")
    return HttpResponse('\n'.join(lines), content_type='text/plain')

urlpatterns = [
    path('admin/', admin.site.urls),
    path('__diag_static__', diag_static),
    path('', include('web.urls')),
]

# EdgeOne 上静态文件通过 WSGI 管道 serve（DEBUG=False，需要显式路由）
# 注意：EdgeOne 会拦截 /static/ 前缀导致 SCF 崩溃，故使用 /assets/
# insecure=True 允许在 DEBUG=False 时使用 staticfiles.views.serve
urlpatterns += [
    re_path(r'^assets/(?P<path>.*)$', static_serve, {'insecure': True}),
]