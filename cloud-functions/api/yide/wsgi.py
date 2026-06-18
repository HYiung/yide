"""
WSGI config for yide project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/wsgi/
"""

import os
import sys
from django.core.wsgi import get_wsgi_application

# 1. 动态获取当前文件的绝对路径
# 这里指向 /var/task/yide/yide/
current_dir = os.path.dirname(os.path.abspath(__file__))

# 2. 获取上一层（包含 manage.py 的那层 yide 目录）
# 这里指向 /var/task/yide/
parent_dir = os.path.dirname(current_dir)

# 3. 强行插入到 Python 查找路径的最前面
# 必须使用 sys.path.insert(0, ...)，不能用 append，确保最高优先级！
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

# 4. 显式指定配置模块名。
# 因为我们把 parent_dir 放进了查找路径，此时 Python 找 'yide.settings'
# 就会完美等同于找：parent_dir 目录下的 'yide/settings.py'
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'yide.settings')

# 👇 云端自动迁移和创建管理员
from django.core.management import call_command

try:
    call_command('migrate', interactive=False)

    from django.contrib.auth.models import User

    if not User.objects.filter(username='admin').exists():
        User.objects.create_superuser('admin', 'admin@example.com', 'Admin123456')
except Exception as e:
    print(f"Auto-migration failed: {e}")

application = get_wsgi_application()
