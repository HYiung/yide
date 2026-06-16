#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys


def main():
    """Run administrative tasks."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'yide.settings')

    # Running from the repository root with ``python yide/manage.py test`` can
    # make unittest discover the outer ``yide`` package and try to import
    # ``yide.web`` / ``yide.yide``. Limit the default test target to the Django
    # app so the command works from both the repo root and the Django project
    # directory.
    if len(sys.argv) == 2 and sys.argv[1] == 'test':
        sys.argv.append('web')

    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
