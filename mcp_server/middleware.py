import contextvars
import json
import logging
import os

from asgiref.sync import sync_to_async
from starlette.datastructures import Headers
from starlette.responses import JSONResponse, Response

logger = logging.getLogger(__name__)

# Context variable binding the authenticated OAuth user to the current async request.
current_mcp_user: contextvars.ContextVar = contextvars.ContextVar("current_mcp_user", default=None)

# Fail-closed allowlist of read-only MCP tools; every other tool call requires the `write` scope.
READ_ONLY_TOOLS = frozenset({
    'get_portfolio_summary',
    'get_portfolio_stocks',
    'get_portfolio_mutual_funds',
    'get_epf_details',
    'get_pf_details',
    'get_nps_details',
    'get_fixed_deposits',
    'get_cash_positions',
    'get_bond_holdings',
    'get_crypto_holdings',
    'get_commodity_holdings',
    'get_us_stock_holdings',
    'get_real_estate_holdings',
    'get_real_estate_detail',
    'get_real_estate_llm_prompt',
    'get_portfolio_goals',
    'get_portfolio_snapshots',
    'get_ai_insights',
    'get_ai_insight_status',
    'get_transactions',
    'get_hra_expenses',
    'get_tracker_goals',
    'get_notes',
    'get_jewellery_items',
    'list_mcp_audit_log',
})
WRITE_TOOL_PREFIXES = ('add_', 'update_', 'delete_', 'revert_', 'trigger_', 'do_')
_MAX_BODY_BYTES = 1_000_000


def _resolve_token_user_and_scopes(token_string: str):
    """Synchronous DB lookup returning (user, scopes_set) or (None, None)."""
    try:
        from oauth2_provider.models import AccessToken
        from tracker.models import AccountGroup
        token = AccessToken.objects.select_related('user', 'user__group').get(token=token_string)
    except Exception as e:
        logger.warning("OAuth token lookup failed: %s", type(e).__name__)
        return None, None
    if not token.is_valid(scopes=['read']):
        return None, None
    user = token.user
    if user is None or not user.is_active:
        logger.warning("MCP token rejected: not bound to an active user")
        return None, None
    served = AccountGroup.objects.order_by('pk').first()  # mirrors server._get_group()
    if served is None or user.group_id != served.pk:
        logger.warning("MCP token rejected: user is outside the served household")
        return None, None
    # MCP tools expose the whole portfolio, which only the primary holder may see.
    if not getattr(user, 'can_view_portfolio', False):
        logger.warning("MCP token rejected: user is not the household's primary holder")
        return None, None
    return user, set((token.scope or '').split())


@sync_to_async
def get_token_scopes(token_string: str):
    """Return the token's scope set if it is valid, grants `read`, and belongs to an
    active user of the household this MCP server serves; else None."""
    user, scopes = _resolve_token_user_and_scopes(token_string)
    if scopes is not None:
        current_mcp_user.set(user)
    return scopes


def _inspect_non_write_payload(body: bytes):
    """Validate JSON-RPC payload when caller lacks `write` scope.

    Returns (parse_error: bool, blocked_calls: list[tuple[Any, str]]).
    Fails closed: malformed JSON or any `tools/call` not in READ_ONLY_TOOLS is blocked.
    """
    if not body or not body.strip():
        return False, []
    try:
        payload = json.loads(body)
    except (ValueError, TypeError):
        return True, []
    messages = payload if isinstance(payload, list) else [payload]
    blocked = []
    for msg in messages:
        if not isinstance(msg, dict):
            return True, []
        if msg.get('method') == 'tools/call':
            params = msg.get('params')
            if not isinstance(params, dict):
                blocked.append((msg.get('id'), '<invalid>'))
                continue
            name = params.get('name', '')
            if not isinstance(name, str) or name not in READ_ONLY_TOOLS:
                blocked.append((msg.get('id'), str(name or '<unknown>')))
    return False, blocked


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

        ctx_tok = current_mcp_user.set(None)
        try:
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
                parse_error, blocked = _inspect_non_write_payload(body)
                if parse_error:
                    response = JSONResponse(
                        {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}},
                        status_code=400,
                    )
                    await response(scope, receive, send)
                    return
                if blocked:
                    req_id, name = blocked[0]
                    logger.warning("MCP tool %s blocked: token lacks write scope", name)
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
        finally:
            current_mcp_user.reset(ctx_tok)
