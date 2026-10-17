"""OAuth hardening for the MCP endpoint: only user-bound (login) grants may mint tokens."""
import json

from oauth2_provider.oauth2_validators import OAuth2Validator

# Grants that always involve an interactive user login. client_credentials / password /
# device_code would let an anonymously registered client obtain a token with no user.
ALLOWED_GRANT_TYPES = frozenset({'authorization_code', 'refresh_token'})


class UserBoundGrantValidator(OAuth2Validator):
    def validate_grant_type(self, client_id, grant_type, client, request, *args, **kwargs):
        if grant_type not in ALLOWED_GRANT_TYPES:
            return False
        return super().validate_grant_type(client_id, grant_type, client, request, *args, **kwargs)


class AuthorizationCodeOnlyDCRPermission:
    """Open dynamic client registration, limited to the authorization_code grant."""

    def has_permission(self, request) -> bool:
        try:
            data = json.loads(request.body or b'{}')
        except ValueError:
            return True  # let the view return its own invalid_client_metadata error
        grant_types = data.get('grant_types', ['authorization_code']) if isinstance(data, dict) else []
        return isinstance(grant_types, list) and set(grant_types) <= ALLOWED_GRANT_TYPES
