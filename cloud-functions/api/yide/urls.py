from django.contrib import admin
from django.urls import path, include, re_path
from django.contrib.staticfiles.views import serve as static_serve

from web import views as web_views

urlpatterns = [
    # 必须放在 admin/ 之前：后台点「退出」后回店长入口，
    # 而不是 Django 默认那个带「重新登录」链接的登出页 / admin 登录页
    path('admin/logout/', web_views.admin_logout, name='admin_logout'),
    path('admin/', admin.site.urls),
    path('', include('web.urls')),
]

# EdgeOne 上静态文件通过 WSGI 管道 serve（DEBUG=False，需要显式路由）
# 注意：EdgeOne 会拦截 /static/ 前缀导致 SCF 崩溃，故使用 /assets/
# insecure=True 允许在 DEBUG=False 时使用 staticfiles.views.serve
urlpatterns += [
    re_path(r'^assets/(?P<path>.*)$', static_serve, {'insecure': True}),
]