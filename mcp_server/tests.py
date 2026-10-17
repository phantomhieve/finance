import asyncio
import json
from unittest import mock

from django.test import SimpleTestCase, TransactionTestCase

from mcp_server import middleware as mw


def _call(scopes, body, method='POST', headers=None, query=b''):
    """Run the middleware once against a stub app; return (status, downstream_body)."""
    seen = {}

    async def app(scope, receive, send):
        msg = await receive()
        seen['body'] = msg.get('body')
        await send({'type': 'http.response.start', 'status': 200, 'headers': []})
        await send({'type': 'http.response.body', 'body': b'ok'})

    sent = []

    async def send(message):
        sent.append(message)

    async def receive():
        return {'type': 'http.request', 'body': body, 'more_body': False}

    scope = {
        'type': 'http', 'method': method, 'path': '/', 'query_string': query,
        'headers': [(b'authorization', b'Bearer abc')] if headers is None else headers, 'scheme': 'https',
    }

    async def run():
        with mock.patch.object(mw, 'get_token_scopes', mock.AsyncMock(return_value=scopes)):
            await mw.OAuthBearerMiddleware(app)(scope, receive, send)

    asyncio.run(run())
    return sent[0]['status'], seen.get('body')


def _rpc(name):
    return json.dumps({'jsonrpc': '2.0', 'id': 7, 'method': 'tools/call', 'params': {'name': name}}).encode()


class OAuthScopeMiddlewareTests(SimpleTestCase):
    def test_invalid_token_rejected(self):
        status, _ = _call(None, _rpc('get_notes'))
        self.assertEqual(status, 401)

    def test_read_scope_can_call_read_tool_and_body_is_replayed(self):
        body = _rpc('get_portfolio_summary')
        status, downstream = _call({'read'}, body)
        self.assertEqual(status, 200)
        self.assertEqual(downstream, body)

    def test_read_scope_blocked_from_write_tool(self):
        status, downstream = _call({'read'}, _rpc('delete_record'))
        self.assertEqual(status, 403)
        self.assertIsNone(downstream)

    def test_write_tool_in_batch_is_blocked(self):
        batch = json.dumps([json.loads(_rpc('get_notes')), json.loads(_rpc('update_note'))]).encode()
        status, _ = _call({'read'}, batch)
        self.assertEqual(status, 403)

    def test_token_in_query_string_is_not_accepted(self):
        status, downstream = _call({'read', 'write'}, _rpc('get_notes'), headers=[], query=b'access_token=abc')
        self.assertEqual(status, 401)
        self.assertIsNone(downstream)

    def test_write_scope_allows_write_tool(self):
        status, _ = _call({'read', 'write'}, _rpc('add_transaction'))
        self.assertEqual(status, 200)


class OAuthTenancyTests(TransactionTestCase):
    """Anonymous clients must not obtain usable tokens; tokens are bound to the served household."""

    def setUp(self):
        from tracker.models import AccountGroup, User
        self.home = AccountGroup.objects.create(name="Home")
        self.other = AccountGroup.objects.create(name="Other")
        self.owner = User.objects.create_user(username="owner", password="x", user_type="PRIMARY", group=self.home)
        self.outsider = User.objects.create_user(username="outsider", password="x", user_type="PRIMARY", group=self.other)

    def _token(self, user, scope='read write'):
        import datetime
        from django.utils import timezone
        from oauth2_provider.models import AccessToken, Application
        app = Application.objects.create(name="t", client_type="public",
                                         authorization_grant_type="authorization-code",
                                         redirect_uris="https://example.com/cb")
        return AccessToken.objects.create(user=user, application=app, token=f"tok-{user and user.pk}-{app.pk}",
                                          scope=scope, expires=timezone.now() + datetime.timedelta(hours=1))

    def _scopes(self, token):
        return asyncio.run(mw.get_token_scopes(token.token))

    def test_dcr_rejects_client_credentials_registration(self):
        resp = self.client.post('/o/register/', data=json.dumps({
            "client_name": "x", "grant_types": ["client_credentials"], "scope": "read write"}),
            content_type='application/json')
        self.assertEqual(resp.status_code, 401)

    def test_token_endpoint_refuses_client_credentials(self):
        from oauth2_provider.models import Application
        app = Application(name="cc", client_type="confidential", authorization_grant_type="client-credentials",
                          client_secret="s3cret-for-test")
        app.save()
        resp = self.client.post('/o/token/', {"grant_type": "client_credentials", "client_id": app.client_id,
                                              "client_secret": "s3cret-for-test", "scope": "read write"})
        self.assertNotEqual(resp.status_code, 200)
        self.assertNotIn('access_token', resp.json())

    def test_token_without_user_is_rejected(self):
        self.assertIsNone(self._scopes(self._token(None)))

    def test_token_from_other_household_is_rejected(self):
        self.assertIsNone(self._scopes(self._token(self.outsider)))

    def test_spouse_and_landlord_tokens_are_rejected(self):
        from tracker.models import User
        for kind in ('ACCOUNT_HOLDER', 'LANDLORD'):
            member = User.objects.create_user(username=kind.lower(), password="x", user_type=kind, group=self.home)
            self.assertIsNone(self._scopes(self._token(member)), kind)

    def test_token_from_served_household_is_accepted(self):
        self.assertEqual(self._scopes(self._token(self.owner)), {'read', 'write'})

    def test_inactive_user_token_is_rejected(self):
        self.owner.is_active = False
        self.owner.save()
        self.assertIsNone(self._scopes(self._token(self.owner)))
