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
            
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            res = Response("Unauthorized - Missing or invalid Bearer token", status_code=401)
            base_url = str(request.base_url).rstrip('/')
            res.headers["WWW-Authenticate"] = f'Bearer resource_metadata="{base_url}/.well-known/oauth-authorization-server"'
            return res
            
        token_string = auth_header.split(" ")[1]
        
        is_valid = await validate_oauth_token(token_string)
        if not is_valid:
            res = Response("Unauthorized - Invalid or expired token", status_code=401)
            base_url = str(request.base_url).rstrip('/')
            res.headers["WWW-Authenticate"] = f'Bearer resource_metadata="{base_url}/.well-known/oauth-authorization-server"'
            return res
            
        return await call_next(request)
