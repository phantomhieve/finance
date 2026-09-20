import logging
from asgiref.sync import sync_to_async
from starlette.datastructures import Headers, QueryParams
from starlette.responses import Response

logger = logging.getLogger(__name__)

@sync_to_async
def validate_oauth_token(token_string: str) -> bool:
    try:
        from oauth2_provider.models import AccessToken
        token = AccessToken.objects.select_related("user").get(token=token_string)
        if token.is_valid(scopes=[]):
            return True
        return False
    except Exception as e:
        logger.warning(f"OAuth token validation failed: {e}")
        return False

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
        query_params = QueryParams(scope.get("query_string", b"").decode("latin-1"))

        token_string = None
        auth_header = headers.get("authorization")
        if auth_header and auth_header.lower().startswith("bearer "):
            token_string = auth_header[7:].strip()
        elif "token" in query_params:
            token_string = query_params["token"]
        elif "access_token" in query_params:
            token_string = query_params["access_token"]

        server_host = headers.get("host", "localhost:8000")
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

        is_valid = await validate_oauth_token(token_string)
        if not is_valid:
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

        await self.app(scope, receive, send)

