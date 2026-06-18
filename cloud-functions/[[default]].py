"""
EdgeOne Pages Catch-All 入口（Handler 模式）
"""
import io, os, sys, traceback
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
        import django
        django.setup()
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
        environ = {
            'REQUEST_METHOD': self.command, 'SCRIPT_NAME': '',
            'PATH_INFO': parsed.path, 'QUERY_STRING': parsed.query,
            'CONTENT_TYPE': self.headers.get('Content-Type', ''),
            'CONTENT_LENGTH': str(content_length),
            'SERVER_NAME': self.headers.get('Host', 'localhost'),
            'SERVER_PORT': '443', 'SERVER_PROTOCOL': self.request_version,
            'wsgi.version': (1,0), 'wsgi.url_scheme': 'https',
            'wsgi.input': io.BytesIO(body), 'wsgi.errors': sys.stderr,
            'wsgi.multithread': True, 'wsgi.multiprocess': False, 'wsgi.run_once': False,
        }
        for k,v in self.headers.items():
            environ['HTTP_'+k.upper().replace('-','_')] = v

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
