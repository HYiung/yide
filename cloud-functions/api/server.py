"""
EdgeOne Pages WSGI 入口 — 导入 Django 应用暴露给平台
"""
import os
import sys

current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'yide.settings')

from yide.wsgi import application
