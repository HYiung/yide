from django.contrib import admin
from django.urls import path, include, re_path
from django.contrib.staticfiles.views import serve as static_serve

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('web.urls')),
]

# EdgeOne 上静态文件通过 WSGI 管道 serve（DEBUG=False，需要显式路由）
# 注意：EdgeOne 会拦截 /static/ 前缀导致 SCF 崩溃，故使用 /assets/
urlpatterns += [
    re_path(r'^assets/(?P<path>.*)$', static_serve),
]