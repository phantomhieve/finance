"""
WSGI config for pftracker project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.0/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application

from pftracker.dotenv import load_dotenv

load_dotenv()
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pftracker.settings')

wsgi_application = get_wsgi_application()

# Since the production systemd service explicitly loads `pftracker.wsgi:application` 
# while `gunicorn.conf.py` uses UvicornWorker (ASGI), we MUST export an ASGI 
# callable as `application` here to prevent 500 Internal Server Errors.
from pftracker.asgi import application
