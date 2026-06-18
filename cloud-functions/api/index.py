"""
EdgeOne Pages WSGI 入口
EdgeOne Cloud Functions 会扫描 entry 目录下的 Python 文件，
查找名为 ``application`` 的可调用对象作为 WSGI 入口。
"""
import os
import sys

# 确保当前目录在 Python 路径中
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'yide.settings')

from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
