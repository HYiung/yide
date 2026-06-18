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
import traceback

# 将 Django 项目目录 api/ 加入 Python 路径
current_dir = os.path.dirname(os.path.abspath(__file__))
api_dir = os.path.join(current_dir, 'api')
if api_dir not in sys.path:
    sys.path.insert(0, api_dir)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'yide.settings')

# ========== 尝试加载 Django（带 fallback 诊断） ==========
_django_ok = False
_django_error = None

try:
    from django.core.wsgi import get_wsgi_application
    # ⚠️ 保持下面这行作为 EdgeOne WSGI 检测标记，不要改成别的变量名
    application = get_wsgi_application()
    _django_ok = True
except Exception as e:
    _django_error = traceback.format_exc()
    print(f"Django init error: {_django_error}", flush=True)
    # 定义 fallback 应用返回诊断信息
    def application(environ, start_response):
        status = '500 Internal Server Error'
        headers = [('Content-Type', 'text/plain; charset=utf-8')]
        start_response(status, headers)
        body = (
            f"ERROR: Django failed to initialize\n\n"
            f"{_django_error}\n\n"
            f"PYTHONPATH: {sys.path[:5]}\n"
            f"PYTHON VERSION: {sys.version}\n"
            f"ENV KEYS: {[k for k in os.environ.keys() if not k.startswith('_')]}\n"
        )
        return [body.encode('utf-8')]
