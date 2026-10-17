import json
import logging
import os

from asgiref.sync import sync_to_async
from starlette.datastructures import Headers
from starlette.responses import JSONResponse, Response

logger = logging.getLogger(__name__)

# Tools whose names start with these mutate data or spend quota → require the `write` scope.
WRITE_TOOL_PREFIXES = ('add_', 'update_', 'delete_', 'revert_', 'trigger_', 'do_')
_MAX_BODY_BYTES = 1_000_000


@sync_to_async
def get_token_scopes(token_string: str):
    """Return the token's scope set if it is valid, grants `read`, and belongs to an
    active user of the household this MCP server serves; else None."""
    try:
        from oauth2_provider.models import AccessToken
        from tracker.models import AccountGroup
        token = AccessToken.objects.select_related('user').get(token=token_string)
    except Exception as e:
        logger.warning("OAuth token lookup failed: %s", type(e).__name__)
        return None
    if not token.is_valid(scopes=['read']):
        return None
    user = token.user
    if user is None or not user.is_active:
        logger.warning("MCP token rejected: not bound to an active user")
        return None
    served = AccountGroup.objects.first()  # mirrors server._get_group()
    if served is None or user.group_id != served.pk:
        logger.warning("MCP token rejected: user is outside the served household")
        return None
    # MCP tools expose the whole portfolio, which only the primary holder may see.
    if not getattr(user, 'can_view_portfolio', False):
        logger.warning("MCP token rejected: user is not the household's primary holder")
        return None
    return set((token.scope or '').split())


def _write_tool_calls(body: bytes):
    """Names of write tools invoked by a JSON-RPC payload (single or batch)."""
    try:
        payload = json.loads(body or b'null')
    except ValueError:
        return []
    messages = payload if isinstance(payload, list) else [payload]
    names = []
    for msg in messages:
        if isinstance(msg, dict) and msg.get('method') == 'tools/call':
            name = (msg.get('params') or {}).get('name', '')
            if isinstance(name, str) and name.startswith(WRITE_TOOL_PREFIXES):
                names.append((msg.get('id'), name))
    return names


async def _read_body(receive):
    chunks, size = [], 0
    while True:
        message = await receive()
        if message['type'] != 'http.request':
            return None
        chunk = message.get('body', b'')
        size += len(chunk)
        if size > _MAX_BODY_BYTES:
            return None
        chunks.append(chunk)
        if not message.get('more_body', False):
            return b''.join(chunks)


class OAuthBearerMiddleware:
    """
    Pure ASGI middleware for OAuth Bearer token validation.
    Avoids BaseHTTPMiddleware to maintain full compatibility with SSE streaming responses.
    """
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Allow OPTIONS for CORS preflight
        if scope.get("method") == "OPTIONS":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)

        # Header only: tokens in the query string end up in proxy and access logs.
        token_string = None
        auth_header = headers.get("authorization")
        if auth_header and auth_header.lower().startswith("bearer "):
            token_string = auth_header[7:].strip()

        server_host = headers.get("host") or os.environ.get("VAULT_HOST", "localhost:8000")
        scheme = "https" if headers.get("x-forwarded-proto") == "https" else scope.get("scheme", "https")
        base_url = f"{scheme}://{server_host}"

        if not token_string:
            response = Response(
                "Unauthorized - Missing Bearer token",
                status_code=401,
                headers={
                    "WWW-Authenticate": f'Bearer resource_metadata="{base_url}/.well-known/oauth-protected-resource"',
                    "Content-Type": "text/plain; charset=utf-8",
                },
            )
            await response(scope, receive, send)
            return

        scopes = await get_token_scopes(token_string)
        if scopes is None:
            response = Response(
                "Unauthorized - Invalid or expired token",
                status_code=401,
                headers={
                    "WWW-Authenticate": f'Bearer error="invalid_token", resource_metadata="{base_url}/.well-known/oauth-protected-resource"',
                    "Content-Type": "text/plain; charset=utf-8",
                },
            )
            await response(scope, receive, send)
            return

        if scope.get("method") == "POST" and "write" not in scopes:
            body = await _read_body(receive)
            if body is None:
                await Response("Request body too large", status_code=413)(scope, receive, send)
                return
            blocked = _write_tool_calls(body)
            if blocked:
                req_id, name = blocked[0]
                logger.warning("MCP write tool %s blocked: token lacks write scope", name)
                response = JSONResponse(
                    {"jsonrpc": "2.0", "id": req_id,
                     "error": {"code": -32001, "message": f"insufficient_scope: '{name}' requires the write scope"}},
                    status_code=403,
                    headers={"WWW-Authenticate": 'Bearer error="insufficient_scope", scope="read write"'},
                )
                await response(scope, receive, send)
                return

            replayed = False

            async def replay_receive():
                nonlocal replayed
                if not replayed:
                    replayed = True
                    return {"type": "http.request", "body": body, "more_body": False}
                return await receive()

            await self.app(scope, replay_receive, send)
            return

        await self.app(scope, receive, send)
