"""
EdgeOne Pages Catch-All WSGI 入口
[[default]].py 是 EdgeOne 的 catch-all 路由模式，
所有 HTTP 请求（/、/admin、/api/* 等）都会先进这个文件，
然后交给 Django 的 WSGI application 做内部路由。
"""
import os
import sys

# 将 Django 项目目录 api/ 加入 Python 路径
# 这样 Python 才能找到 yide.settings、yide.urls 等模块
current_dir = os.path.dirname(os.path.abspath(__file__))
api_dir = os.path.join(current_dir, 'api')
if api_dir not in sys.path:
    sys.path.insert(0, api_dir)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'yide.settings')

# 导入 yide.wsgi 触发云端自动迁移（migrate + 创建管理员）
import yide.wsgi

from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
