import logging
from asgiref.sync import sync_to_async
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

logger = logging.getLogger(__name__)

@sync_to_async
def validate_oauth_token(token_string: str) -> bool:
    try:
        from oauth2_provider.models import AccessToken
        from django.utils import timezone
        
        token = AccessToken.objects.select_related("user").get(token=token_string)
        if token.is_valid(scopes=[]):
            return True
        return False
    except Exception as e:
        logger.warning(f"OAuth token validation failed: {e}")
        return False

class OAuthBearerMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        # Allow OPTIONS for CORS preflight
        if request.method == "OPTIONS":
            return await call_next(request)
            
        token_string = None
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token_string = auth_header.split(" ", 1)[1].strip()
        elif "token" in request.query_params:
            token_string = request.query_params.get("token")
        elif "access_token" in request.query_params:
            token_string = request.query_params.get("access_token")

        if not token_string:
            res = Response("Unauthorized - Missing Bearer token", status_code=401)
            base_url = str(request.base_url).rstrip('/')
            res.headers["WWW-Authenticate"] = f'Bearer resource_metadata="{base_url}/.well-known/oauth-protected-resource"'
            return res
            
        is_valid = await validate_oauth_token(token_string)
        if not is_valid:
            res = Response("Unauthorized - Invalid or expired token", status_code=401)
            base_url = str(request.base_url).rstrip('/')
            res.headers["WWW-Authenticate"] = f'Bearer error="invalid_token", resource_metadata="{base_url}/.well-known/oauth-protected-resource"'
            return res
            
        return await call_next(request)
