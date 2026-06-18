"""WSGI test — 验证 EdgeOne 能否检测 Django-style WSGI application"""
import sys

def application(environ, start_response):
    status = '200 OK'
    headers = [('Content-Type', 'text/plain')]
    start_response(status, headers)
    return [
        b"WSGI application works!\n",
        f"PATH_INFO: {environ.get('PATH_INFO', 'N/A')}\n".encode(),
        f"SCRIPT_NAME: {environ.get('SCRIPT_NAME', 'N/A')}\n".encode(),
        f"sys.path: {sys.path[:5]}\n".encode(),
    ]
