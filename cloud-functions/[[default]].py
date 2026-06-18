"""
EdgeOne Pages Catch-All WSGI 入口

[[default]].py 是 EdgeOne 的 catch-all 路由模式，
匹配 cloud-functions/ 根目录下的所有路径（/*）。
所有 HTTP 请求都会经过 Django WSGI application 做内部路由。

⚠️ 注意：不要 import yide.wsgi，否则会引起 Django populate() reentrancy。
只有此文件调用 get_wsgi_application()。
"""
import os
import sys

# 将 Django 项目目录 api/ 加入 Python 路径
current_dir = os.path.dirname(os.path.abspath(__file__))
api_dir = os.path.join(current_dir, 'api')
if api_dir not in sys.path:
    sys.path.insert(0, api_dir)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'yide.settings')

from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()

# ========== 冷启动自动迁移 ==========
import django
from django.core.management import call_command
try:
    call_command('migrate', interactive=False, run_syncdb=True)
    from django.contrib.auth.models import User
    if not User.objects.filter(username='admin').exists():
        User.objects.create_superuser('admin', 'admin@example.com', 'Admin123456')
except Exception as e:
    print(f"Auto-migration skipped: {e}")
