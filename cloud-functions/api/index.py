"""
Django 项目辅助模块（非 WSGI 入口）

⚠️ 注意：WSGI 入口已迁移到父目录的 [[default]].py，
EdgeOne Pages 通过 catch-all 路由将所有请求转发到 Django。
此文件仅供本地开发和 Django 内部引用使用。
"""
import os
import sys

# 确保当前目录在 Python 路径中
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'yide.settings')
