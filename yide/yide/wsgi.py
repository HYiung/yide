"""
WSGI config for yide project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/3.2/howto/deployment/wsgi/
"""

# yide/yide/wsgi.py

import os
import sys
from django.core.wsgi import get_wsgi_application

# 👈 终极绝招：强行把外层的 yide 文件夹加入到 Python 的查找路径中
# 这样不管是找 yide.settings 还是 yide.yide.settings，Python 都能找到了
current_dir = os.path.dirname(os.path.abspath(__file__)) # 这一层是第二个yide
parent_dir = os.path.dirname(current_dir)               # 这一层是第一个yide
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)
    sys.path.insert(0, current_dir) # 保险起见，两层都塞进去

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'yide.settings')

application = get_wsgi_application()
