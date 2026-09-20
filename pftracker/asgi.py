"""
ASGI config for pftracker project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.0/howto/deployment/asgi/
"""

import os

from django.core.asgi import get_asgi_application
from pftracker.dotenv import load_dotenv

load_dotenv()
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pftracker.settings')

# 1. Initialize Django app FIRST
django_app = get_asgi_application()

# 2. Imports that depend on Django being initialized
from starlette.applications import Starlette
from starlette.routing import Mount
from mcp_server.server import mcp
from mcp_server.middleware import OAuthBearerMiddleware

# 3. Setup MCP App with our new OAuth middleware
mcp_app = mcp.sse_app()
mcp_app.add_middleware(OAuthBearerMiddleware)

# 4. Mount together
application = Starlette(routes=[
    Mount("/mcp", app=mcp_app),
    Mount("/", app=django_app)
])
