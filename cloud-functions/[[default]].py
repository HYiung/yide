"""
EdgeOne Pages Catch-All 入口（Handler 模式）
"""
import io, os, sys, traceback, mimetypes
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse

current_dir = os.path.dirname(os.path.abspath(__file__))
api_dir = os.path.join(current_dir, 'api')
if api_dir not in sys.path:
    sys.path.insert(0, api_dir)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'yide.settings')

_django_app = None
_init_error = None

def _init_django():
    global _django_app, _init_error
    if _django_app is not None or _init_error is not None:
        return
    try:
        # 先做迁移（必须在 WSGIHandler 创建之前，否则 app registry 冲突）
        if os.environ.get('CLOUD_DATABASE_URL'):
            try:
                import django
                django.setup()  # 先 setup 再 migrate
                from django.core.management import call_command
                call_command('makemigrations', '--noinput', verbosity=0)
                call_command('migrate', '--noinput', verbosity=0)
                print("Migrations completed on startup", flush=True)
            except Exception as e_mig:
                # 迁移失败时打印警告但不阻塞
                print(f"Migration warning (non-fatal): {e_mig}", flush=True)

        # EdgeOne 环境已预初始化 Django，直接获取 WSGI handler
        from django.core.handlers.wsgi import WSGIHandler
        _django_app = WSGIHandler()
        print("Django initialized successfully", flush=True)
    except Exception as e:
        _init_error = traceback.format_exc()
        print(f"Django init error: {_init_error}", flush=True)

class handler(BaseHTTPRequestHandler):
    def do_GET(self): self._handle_request()
    def do_POST(self): self._handle_request()
    def do_PUT(self): self._handle_request()
    def do_DELETE(self): self._handle_request()

    def _handle_request(self):
        _init_django()

        # === 诊断端点 ===
        if urlparse(self.path).path == '/__diag__':
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.end_headers()
            lines = [
                f"METHOD: {self.command}",
                f"PATH: {self.path}",
                f"ALL_HOSTS: {_django_app is not None}",
            ]
            for k, v in sorted(self.headers.items()):
                lines.append(f"HEADER {k}: {v}")
            self.wfile.write('\n'.join(lines).encode())
            return

        # === 追踪端点（诊断 Django 500 错误） ===
        if urlparse(self.path).path == '/__trace__':
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.end_headers()
            lines = []
            try:
                import django
                lines.append(f"Django version: {django.get_version()}")

                from django.conf import settings
                lines.append(f"DEBUG: {settings.DEBUG}")
                lines.append(f"BASE_DIR: {settings.BASE_DIR}")
                lines.append(f"ALLOWED_HOSTS: {settings.ALLOWED_HOSTS}")
                lines.append(f"INSTALLED_APPS: {settings.INSTALLED_APPS}")

                db = settings.DATABASES.get('default', {})
                lines.append(f"DB engine: {db.get('ENGINE', 'N/A')}")
                lines.append(f"DB name: {db.get('NAME', 'N/A')}")

                try:
                    from django.db import connections
                    connections['default'].ensure_connection()
                    lines.append("DB connection: OK")
                except Exception as dberr:
                    lines.append(f"DB connection: FAILED - {dberr}")

            except Exception as e:
                lines.append(f"TRACE ERROR: {e}")
                lines.append(traceback.format_exc())

            self.wfile.write('\n'.join(lines).encode())
            return

        # === 手动触发迁移端点（先 makemigrations 再 migrate） ===
        if urlparse(self.path).path == '/__migrate__':
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.end_headers()
            msgs = []
            try:
                from django.core.management import call_command
                from io import StringIO
                out = StringIO()
                call_command('makemigrations', '--noinput', stdout=out, stderr=out)
                msgs.append(f"Makemigrations:\n{out.getvalue()}")
                out = StringIO()
                call_command('migrate', '--noinput', stdout=out, stderr=out)
                msgs.append(f"Migrate:\n{out.getvalue()}")
            except Exception as e:
                msgs.append(f"Migration error: {e}\n{traceback.format_exc()}")
            self.wfile.write('\n'.join(msgs).encode())
            return

        # === 模板渲染测试端点 ===
        if urlparse(self.path).path == '/__test_view__':
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.end_headers()
            msgs = []
            try:
                # 只检查模板是否能加载
                from django.template.loader import get_template
                from django.template import TemplateDoesNotExist
                try:
                    tmpl = get_template('cashier.html')
                    msgs.append(f"Template found: {tmpl.origin.name}")
                except TemplateDoesNotExist as e:
                    msgs.append(f"Template NOT FOUND: {e}")
                    msgs.append("Apps loaded:")
                    from django.apps import apps
                    for app_config in apps.get_app_configs():
                        msgs.append(f"  App '{app_config.label}': path={app_config.path}")
                # 尝试渲染
                from django.template import engines
                engine = engines['django']
                tmpl = engine.get_template('cashier.html')
                rendered = tmpl.render({}, request=None)  # 无模板标签，无需 context
                msgs.append(f"Render OK: {len(rendered)} bytes")
            except Exception as e:
                msgs.append(f"Render error: {e}")
                msgs.append(traceback.format_exc())
            self.wfile.write('\n'.join(msgs).encode())
            return

        # === 诊断静态文件查找 ===
        if urlparse(self.path).path == '/__static_diag__':
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.end_headers()
            lines = []
            try:
                from django.contrib.staticfiles import finders
                from django.conf import settings
                lines.append(f"STATIC_URL: {settings.STATIC_URL}")
                lines.append(f"STATIC_ROOT: {getattr(settings, 'STATIC_ROOT', 'N/A')}")
                lines.append(f"STATICFILES_DIRS: {getattr(settings, 'STATICFILES_DIRS', [])}")
                lines.append(f"STATICFILES_FINDERS: {getattr(settings, 'STATICFILES_FINDERS', 'default')}")
                # test finders.find()
                test_path = 'admin/css/base.css'
                lines.append(f"--- Testing finders.find('{test_path}') ---")
                try:
                    abs_path = finders.find(test_path)
                    lines.append(f"Result: {abs_path}")
                    if abs_path:
                        import os
                        lines.append(f"File exists: {os.path.exists(abs_path)}")
                        lines.append(f"File size: {os.path.getsize(abs_path)}")
                except Exception as e_find:
                    lines.append(f"finders.find error: {e_find}")
                    lines.append(traceback.format_exc())
                # test import django to find path
                import django
                lines.append(f"--- Django location ---")
                lines.append(f"Django file: {django.__file__}")
                import os
                django_dir = os.path.dirname(django.__file__)
                admin_static = os.path.join(django_dir, 'contrib', 'admin', 'static', 'admin', 'css', 'base.css')
                lines.append(f"Admin base.css: {admin_static}")
                lines.append(f"Admin base.css exists: {os.path.exists(admin_static)}")
            except Exception as e:
                lines.append(f"Static diag error: {e}")
                lines.append(traceback.format_exc())
            self.wfile.write('\n'.join(lines).encode())
            return

        # === 静态文件服务：让 Django WSGI 处理（staticfiles 的 serve view） ===
        parsed = urlparse(self.path)
        if parsed.path.startswith('/static/'):
            try:
                # 复用 WSGI 管道让 Django 处理 /static/ 路径
                content_length = int(self.headers.get('Content-Length', 0))
                body = self.rfile.read(content_length) if content_length > 0 else b''

                real_host = self.headers.get('Eo-Pages-Host') or self.headers.get('Host', 'localhost')

                environ = {
                    'REQUEST_METHOD': self.command, 'SCRIPT_NAME': '',
                    'PATH_INFO': parsed.path, 'QUERY_STRING': parsed.query,
                    'CONTENT_TYPE': self.headers.get('Content-Type', ''),
                    'CONTENT_LENGTH': str(content_length),
                    'SERVER_NAME': real_host,
                    'SERVER_PORT': '443', 'SERVER_PROTOCOL': self.request_version,
                    'wsgi.version': (1,0), 'wsgi.url_scheme': 'https',
                    'wsgi.input': io.BytesIO(body), 'wsgi.errors': sys.stderr,
                    'wsgi.multithread': True, 'wsgi.multiprocess': False, 'wsgi.run_once': False,
                }
                for k,v in self.headers.items():
                    environ['HTTP_'+k.upper().replace('-','_')] = v
                environ['HTTP_HOST'] = real_host

                status = None; resp_hdrs = []
                def start_response(s, h, exc_info=None):
                    nonlocal status, resp_hdrs; status = s; resp_hdrs = h

                result = _django_app(environ, start_response)
                if status:
                    self.send_response(int(status.split()[0]))
                    for n,v in resp_hdrs:
                        if n.lower() not in ('transfer-encoding','connection','keep-alive','upgrade'):
                            self.send_header(n,v)
                    self.end_headers()
                    for chunk in result:
                        self.wfile.write(chunk if isinstance(chunk, bytes) else chunk.encode())
                else:
                    self.send_response(500); self.end_headers()
                    self.wfile.write(b"Django no response for static file")
                if hasattr(result, 'close'): result.close()
            except Exception as e:
                self.send_response(500)
                self.send_header('Content-Type', 'text/plain; charset=utf-8')
                self.end_headers()
                err_body = f'Static file WSGI error: {e}\n{traceback.format_exc()}'.encode('utf-8')
                self.wfile.write(err_body)
            return

        if _init_error:
            self.send_response(500)
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.end_headers()
            body = f"ERROR: Django init failed\n\n{_init_error}\nPYTHONPATH: {sys.path[:5]}\n"
            self.wfile.write(body.encode())
            return
        if _django_app is None:
            self.send_response(503)
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.end_headers()
            self.wfile.write(b"Django initializing...\n")
            return

        parsed = urlparse(self.path)
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length) if content_length > 0 else b''

        # EdgeOne 的 Host 头是内部域名，用 Eo-Pages-Host 获取用户真实域名
        real_host = self.headers.get('Eo-Pages-Host') or self.headers.get('Host', 'localhost')

        environ = {
            'REQUEST_METHOD': self.command, 'SCRIPT_NAME': '',
            'PATH_INFO': parsed.path, 'QUERY_STRING': parsed.query,
            'CONTENT_TYPE': self.headers.get('Content-Type', ''),
            'CONTENT_LENGTH': str(content_length),
            'SERVER_NAME': real_host,
            'SERVER_PORT': '443', 'SERVER_PROTOCOL': self.request_version,
            'wsgi.version': (1,0), 'wsgi.url_scheme': 'https',
            'wsgi.input': io.BytesIO(body), 'wsgi.errors': sys.stderr,
            'wsgi.multithread': True, 'wsgi.multiprocess': False, 'wsgi.run_once': False,
        }
        for k,v in self.headers.items():
            environ['HTTP_'+k.upper().replace('-','_')] = v
        # 覆盖 HTTP_HOST 为真实域名（否则 Django ALLOWED_HOSTS 会拒绝）
        environ['HTTP_HOST'] = real_host

        status = None; resp_hdrs = []
        def start_response(s, h, exc_info=None):
            nonlocal status, resp_hdrs; status = s; resp_hdrs = h

        try:
            result = _django_app(environ, start_response)
            if status:
                self.send_response(int(status.split()[0]))
                for n,v in resp_hdrs:
                    if n.lower() not in ('transfer-encoding','connection','keep-alive','upgrade'):
                        self.send_header(n,v)
                self.end_headers()
                for chunk in result:
                    self.wfile.write(chunk if isinstance(chunk, bytes) else chunk.encode())
            else:
                self.send_response(500); self.end_headers()
                self.wfile.write(b"Django no response")
        except Exception as e:
            self.send_response(500)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            self.wfile.write(f"Django error: {e}\n{traceback.format_exc()}".encode())
        finally:
            if hasattr(result, 'close'): result.close()
