from django.contrib import admin
from django.urls import path, include  # 建议使用 path，更简洁

urlpatterns = [
    path('admin/', admin.site.urls),
    # 将原来的 'web/' 改为 ''，这样访问 http://127.0.0.1:8000 就会进入 web app
    path('', include('web.urls')), 
]