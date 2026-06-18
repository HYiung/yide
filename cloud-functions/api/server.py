"""
EdgeOne Pages WSGI 入口 — 直接创建 Django WSGI 应用
（不导入 wsgi.py，避免模块导入时自动执行迁移）
"""
import os
import sys

current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'yide.settings')

from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
