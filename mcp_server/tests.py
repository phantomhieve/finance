import asyncio
import datetime
from decimal import Decimal
import json
from unittest import mock

from asgiref.sync import async_to_sync
from django.test import SimpleTestCase, TestCase

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


class OAuthTenancyTests(TestCase):
    """Anonymous clients must not obtain usable tokens; tokens are bound to the served household."""

    def setUp(self):
        from tracker.models import AccountGroup, User
        self.home = AccountGroup.objects.create(name="Home")
        self.other = AccountGroup.objects.create(name="Other")
        self.owner = User.objects.create_user(username="owner", password="x", user_type="PRIMARY", group=self.home)
        self.outsider = User.objects.create_user(username="outsider", password="x", user_type="PRIMARY", group=self.other)

    def tearDown(self):
        mw.current_mcp_user.set(None)

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
        return async_to_sync(mw.get_token_scopes)(token.token)

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


class MCPServerToolsAndResourcesTests(TestCase):
    def setUp(self):
        from tracker.models import AccountGroup, User
        from portfolio.models import ZerodhaAccount, StockHolding, MutualFundHolding
        self.group = AccountGroup.objects.create(name="Primary Family")
        self.primary = User.objects.create_user(
            username="mcp_primary", password="x", user_type="PRIMARY", group=self.group
        )
        self.acct = ZerodhaAccount.objects.create(group=self.group, name="Main Kite", slug="main-kite")
        self.stock = StockHolding.objects.create(
            account=self.acct,
            symbol="INFY",
            quantity=50,
            purchase_value=Decimal('70000.00'),
            current_value=Decimal('85000.00'),
            is_baby=False,
        )
        self.mf = MutualFundHolding.objects.create(
            account=self.acct,
            fund_name="UTI Nifty 50 Index Fund",
            fund_type="INDEX",
            units=Decimal('500.00'),
            purchase_value=Decimal('60000.00'),
            current_value=Decimal('75000.00'),
            is_baby=False,
        )

    def test_portfolio_stocks_resource_returns_valid_json_and_values(self):
        from mcp_server.server import portfolio_stocks
        raw = portfolio_stocks()
        data = json.loads(raw)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['symbol'], 'INFY')
        self.assertEqual(data[0]['account'], 'Main Kite')
        self.assertEqual(data[0]['current_value'], '85000.00')

    def test_portfolio_mutual_funds_resource_returns_valid_json(self):
        from mcp_server.server import portfolio_mutual_funds
        raw = portfolio_mutual_funds()
        data = json.loads(raw)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['fund_name'], 'UTI Nifty 50 Index Fund')
        self.assertEqual(data[0]['fund_type'], 'INDEX')
        self.assertEqual(data[0]['current_value'], '75000.00')

    def test_get_portfolio_stocks_tool_filtering(self):
        from mcp_server.server import get_portfolio_stocks
        # Matching symbol
        res = json.loads(get_portfolio_stocks(symbol='INF'))
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]['symbol'], 'INFY')

        # Non-matching symbol
        res_none = json.loads(get_portfolio_stocks(symbol='TCS'))
        self.assertEqual(len(res_none), 0)

    def test_get_portfolio_mutual_funds_tool_filtering(self):
        from mcp_server.server import get_portfolio_mutual_funds
        res = json.loads(get_portfolio_mutual_funds(fund_name='Nifty'))
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]['fund_name'], 'UTI Nifty 50 Index Fund')

        res_none = json.loads(get_portfolio_mutual_funds(fund_name='Midcap'))
        self.assertEqual(len(res_none), 0)

    def test_parse_helpers_resilience(self):
        import datetime
        from decimal import Decimal
        from mcp_server.server import _parse_date, _parse_decimal

        # Valid dates
        self.assertEqual(_parse_date("2026-06-15"), datetime.date(2026, 6, 15))

        # Invalid dates fallback to default or today
        fallback = datetime.date(2025, 1, 1)
        self.assertEqual(_parse_date("not-a-date", default=fallback), fallback)
        self.assertEqual(_parse_date("", default=fallback), fallback)
        self.assertEqual(_parse_date(None, default=fallback), fallback)

        # Decimal parsing
        self.assertEqual(_parse_decimal("123.45"), Decimal('123.45'))
        self.assertEqual(_parse_decimal("invalid"), Decimal('0'))
        self.assertEqual(_parse_decimal(None), Decimal('0'))

    def test_audit_logging_create_update_delete_snapshots(self):
        from mcp_server.audit import log_create, log_update, log_delete
        from mcp_server.models import MCPAuditLog
        from tracker.models import Note

        note = Note.objects.create(
            user=self.primary,
            title="Audit Test Note",
            body="Initial Body",
            date=datetime.date(2026, 6, 1),
            financial_year=2026,
        )

        # 1. Log create
        log_create(note, 'add_note')
        c_log = MCPAuditLog.objects.filter(model_name='tracker.Note', action='CREATE').first()
        self.assertIsNotNone(c_log)
        self.assertEqual(c_log.data_after['title'], 'Audit Test Note')
        self.assertIsNone(c_log.data_before)

        # 2. Log update
        from mcp_server.audit import serialize_instance
        before_state = serialize_instance(note)
        note.body = "Modified Body"
        note.save(update_fields=['body'])
        log_update(note, before_state, 'update_note')
        u_log = MCPAuditLog.objects.filter(model_name='tracker.Note', action='UPDATE').first()
        self.assertIsNotNone(u_log)
        self.assertEqual(u_log.data_before['body'], 'Initial Body')
        self.assertEqual(u_log.data_after['body'], 'Modified Body')

        # 3. Log delete
        log_delete(note, 'delete_note')
        d_log = MCPAuditLog.objects.filter(model_name='tracker.Note', action='DELETE').first()
        self.assertIsNotNone(d_log)
        self.assertEqual(d_log.data_before['title'], 'Audit Test Note')
        self.assertIsNone(d_log.data_after)

    def test_read_only_scope_allowlist_blocks_unknown_tools_and_malformed_json(self):
        # Unknown/future tool must be blocked under read-only scope (fail-closed allowlist)
        status_unknown, downstream = _call({'read'}, _rpc('future_unregistered_mutation_tool'))
        self.assertEqual(status_unknown, 403)
        self.assertIsNone(downstream)

        # Malformed JSON body under read-only scope must return 400 (never pass through)
        status_bad_json, downstream_bad = _call({'read'}, b'{not-valid-json')
        self.assertEqual(status_bad_json, 400)
        self.assertIsNone(downstream_bad)

    def test_private_spouse_notes_isolated_from_mcp_tools_and_resources(self):
        from mcp_server.server import delete_record, get_notes, tracker_notes, update_note
        from tracker.models import Note, User

        spouse = User.objects.create_user(
            username="mcp_spouse", password="x", user_type="ACCOUNT_HOLDER", group=self.group
        )
        primary_note = Note.objects.create(
            user=self.primary, title="Primary Note", body="Visible",
            date=datetime.date(2026, 6, 1), financial_year=2026,
        )
        spouse_note = Note.objects.create(
            user=spouse, title="Spouse Private Note", body="Top Secret",
            date=datetime.date(2026, 6, 1), financial_year=2026,
        )

        # Resource & tool must only return PRIMARY user's own notes
        res_notes = json.loads(tracker_notes())
        self.assertEqual([n['id'] for n in res_notes], [primary_note.pk])
        tool_notes = json.loads(get_notes())
        self.assertEqual([n['id'] for n in tool_notes], [primary_note.pk])

        # Attempting to update or delete spouse's note must fail closed
        upd = update_note(note_id=spouse_note.pk, title="Hijacked")
        self.assertTrue(upd.startswith("Error:"))
        spouse_note.refresh_from_db()
        self.assertEqual(spouse_note.title, "Spouse Private Note")

        dele = delete_record('tracker.Note', spouse_note.pk)
        self.assertTrue(dele.startswith("Error:"))
        self.assertTrue(Note.objects.filter(pk=spouse_note.pk).exists())

    def test_audit_revert_fails_closed_on_other_group_and_disallowed_model(self):
        from mcp_server.audit import revert_entry
        from mcp_server.models import MCPAuditLog
        from tracker.models import AccountGroup, Note, User

        # 1. group=None fails closed
        fake_log = MCPAuditLog.objects.create(
            tool_name='add_note', action='CREATE', model_name='tracker.Note',
            object_id=99999, data_after={'id': 99999, 'user_id': self.primary.pk},
        )
        res_no_group = revert_entry(fake_log, group=None)
        self.assertTrue(res_no_group.startswith("Error:"))

        # 2. Disallowed model fails closed
        bad_model_log = MCPAuditLog.objects.create(
            tool_name='evil', action='DELETE', model_name='tracker.User',
            object_id=99999, data_before={'id': 99999, 'group_id': self.group.pk},
        )
        res_bad_model = revert_entry(bad_model_log, group=self.group)
        self.assertTrue(res_bad_model.startswith("Error:"))

        # 3. Cross-household audit entry cannot be reverted by self.group
        other_group = AccountGroup.objects.create(name="OtherAuditGroup")
        outsider = User.objects.create_user(
            username="audit_outsider", password="x", user_type="PRIMARY", group=other_group
        )
        other_note = Note.objects.create(
            user=outsider, title="Outsider Note", body="x",
            date=datetime.date(2026, 6, 1), financial_year=2026,
        )
        cross_log = MCPAuditLog.objects.create(
            tool_name='add_note', action='CREATE', model_name='tracker.Note',
            object_id=other_note.pk,
            data_after={'id': other_note.pk, 'user_id': outsider.pk, 'title': 'Outsider Note'},
        )
        res_cross = revert_entry(cross_log, group=self.group)
        self.assertTrue(res_cross.startswith("Error:"))
        self.assertTrue(Note.objects.filter(pk=other_note.pk).exists())


