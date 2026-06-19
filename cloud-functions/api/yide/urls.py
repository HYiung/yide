from django.contrib import admin
from django.urls import path, include, re_path
from django.contrib.staticfiles.views import serve as static_serve

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('web.urls')),
]

# EdgeOne 上静态文件通过 WSGI 管道 serve（DEBUG=False，需要显式路由）
urlpatterns += [
    re_path(r'^static/(?P<path>.*)$', static_serve),
]