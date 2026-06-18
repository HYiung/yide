"""
EdgeOne Catch-All Handler — 诊断模式
"""
from http.server import BaseHTTPRequestHandler

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type', 'text/plain')
        self.end_headers()
        msg = (
            f"Catch-all works!\n"
            f"PATH: {self.path}\n"
            f"command: {self.command}\n"
        )
        self.wfile.write(msg.encode())

    do_POST = do_GET
    do_PUT = do_GET
    do_DELETE = do_GET
