"""
ASGI config for pftracker project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.0/howto/deployment/asgi/
"""

import contextlib
import os

from django.core.asgi import get_asgi_application
from pftracker.dotenv import load_dotenv

load_dotenv()
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pftracker.settings')

# 1. Initialize Django app FIRST
django_app = get_asgi_application()

# 2. Imports that depend on Django being initialized
from starlette.applications import Starlette
from starlette.datastructures import MutableHeaders
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.routing import Mount

from mcp.server.transport_security import TransportSecuritySettings
from mcp_server.server import mcp
from mcp_server.middleware import OAuthBearerMiddleware

# 3. Setup MCP Apps (SSE + Streamable HTTP)
transport_security = TransportSecuritySettings(enable_dns_rebinding_protection=False)

# SSE app for legacy GET /sse and POST /messages
sse_app = mcp.sse_app(
    message_path="/messages/",
    transport_security=transport_security,
)

# Streamable HTTP app for modern MCP clients (e.g. Google Gemini Custom Connected Apps)
streamable_app = mcp.streamable_http_app(
    streamable_http_path="/",
    transport_security=transport_security,
    json_response=True,
    stateless_http=True,
)

session_manager = mcp._lowlevel_server._session_manager


@contextlib.asynccontextmanager
async def lifespan(app: Starlette):
    async with session_manager.run():
        yield


class MCPRouterApp:
    """
    Router that dispatches incoming MCP requests:
    - Legacy SSE GET (/mcp/sse) -> SSE app
    - Legacy SSE message posting (/mcp/messages/) -> SSE app
    - Modern Streamable HTTP / JSON-RPC over HTTP (POST /mcp/sse, POST /mcp, POST /mcp/) -> Streamable HTTP app
    """
    def __init__(self, sse, streamable):
        self.sse_app = sse
        self.streamable_app = streamable

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.streamable_app(scope, receive, send)
            return

        path = scope.get("path", "")
        method = scope.get("method", "GET")

        # Normalize Accept header so strict checks in the MCP SDK never reject valid clients
        raw_headers = list(scope.get("headers", []))
        has_accept = False
        for i, (k, v) in enumerate(raw_headers):
            if k.lower() == b"accept":
                has_accept = True
                if b"*/*" not in v and b"application/json" not in v:
                    raw_headers[i] = (k, v + b", application/json, text/event-stream, */*")
                break
        if not has_accept:
            raw_headers.append((b"accept", b"application/json, text/event-stream, */*"))
        scope["headers"] = raw_headers

        # Legacy SSE stream connection
        if method == "GET" and (path.endswith("/sse") or path == "/sse"):
            await self.sse_app(scope, receive, send)
            return

        # Legacy SSE message posting
        if "messages" in path:
            await self.sse_app(scope, receive, send)
            return

        # Streamable HTTP (JSON-RPC over HTTP) - reset path to '/' for the sub-app
        new_scope = dict(scope)
        new_scope["path"] = "/"
        await self.streamable_app(new_scope, receive, send)


# CORS is scoped to /mcp only. Bearer tokens travel in headers, so cookies are never
# needed cross-origin; Django routes get CORS from django-cors-headers (CORS_URLS_REGEX).
mcp_app = Starlette(
    routes=[
        Mount("/", app=MCPRouterApp(sse_app, streamable_app))
    ],
    middleware=[
        Middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=False,
            allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
            allow_headers=["*"],
            expose_headers=["Mcp-Session-Id", "WWW-Authenticate"],
        ),
        Middleware(OAuthBearerMiddleware),
    ]
)


class NoBufferMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        async def custom_send(message):
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                if headers.get("content-type") == "text/event-stream":
                    headers.append("X-Accel-Buffering", "no")
            await send(message)

        return await self.app(scope, receive, custom_send)


# 4. Mount together with Lifespan
application = Starlette(
    routes=[
        Mount("/mcp", app=mcp_app),
        Mount("/", app=django_app),
    ],
    middleware=[
        Middleware(NoBufferMiddleware),
    ],
    lifespan=lifespan
)
