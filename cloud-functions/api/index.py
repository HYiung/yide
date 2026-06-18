"""
EdgeOne Pages 入口文件 — 将 Django WSGI 应用暴露给平台
"""
import os
import sys

# 将当前目录加入 Python 路径，使 yide.settings 可被找到
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'yide.settings')

from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
