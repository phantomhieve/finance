"""Unit and integration tests for pftracker core utilities and concurrency framework."""
import asyncio
import datetime
from decimal import Decimal

from django.test import RequestFactory, TestCase

from pftracker.concurrency import (
    DjangoSafeThreadPoolExecutor,
    parallel_map,
    safe_async_to_thread,
)
from pftracker.utils import (
    feature_enabled,
    fy_label,
    fy_start_from_label,
    fy_start_year,
    pct,
    pnl_pct,
    safe_redirect,
)
from tracker.models import AccountGroup, User


class PftrackerUtilsTests(TestCase):
    def setUp(self):
        self.rf = RequestFactory()

    def test_pct_and_pnl_pct_mixed_types_and_edge_cases(self):
        # Normal Decimal
        self.assertEqual(pct(Decimal('25'), Decimal('100')), Decimal('25.00'))

        # Mixed Decimal and float (guarantees no TypeError)
        self.assertEqual(pct(Decimal('30'), 150.0), Decimal('20.00'))
        self.assertEqual(pct(50.0, Decimal('200')), Decimal('25.00'))

        # Mixed int and int
        self.assertEqual(pct(1, 3), Decimal('33.33'))

        # Zero denominator returns Decimal('0')
        self.assertEqual(pct(Decimal('100'), Decimal('0')), Decimal('0'))
        self.assertEqual(pct(100, 0), Decimal('0'))
        self.assertEqual(pct(100, None), Decimal('0'))

        # Negative numbers
        self.assertEqual(pnl_pct(Decimal('-25'), Decimal('100')), Decimal('-25.00'))

        # Non-numeric string gracefully returns Decimal('0')
        self.assertEqual(pct('abc', 'def'), Decimal('0'))

    def test_indian_fiscal_year_helpers(self):
        # April starts new FY
        apr1 = datetime.date(2026, 4, 1)
        self.assertEqual(fy_start_year(apr1), 2026)
        self.assertEqual(fy_label(2026), "FY 2026-27")

        # March belongs to previous year's FY
        mar31 = datetime.date(2026, 3, 31)
        self.assertEqual(fy_start_year(mar31), 2025)

        # Inverses
        self.assertEqual(fy_start_from_label("FY 2026-27"), 2026)
        self.assertEqual(fy_start_from_label("FY 2024-25"), 2024)

        # Malformed labels return None
        self.assertIsNone(fy_start_from_label("FY 2025-25"))
        self.assertIsNone(fy_start_from_label("Long Term"))
        self.assertIsNone(fy_start_from_label(""))
        self.assertIsNone(fy_start_from_label(None))

    def test_safe_redirect_security(self):
        req = self.rf.get('/', HTTP_HOST='testserver')

        # 1. Allowed relative path
        req_safe = self.rf.post('/', {'next': '/tracker/'}, HTTP_HOST='testserver')
        resp = safe_redirect(req_safe, 'dashboard')
        self.assertEqual(resp.url, '/tracker/')

        # 2. Protocol-relative URL attempt (//evil.com) -> blocked, falls back to dashboard
        req_proto = self.rf.post('/', {'next': '//evil.com/phish'}, HTTP_HOST='testserver')
        resp = safe_redirect(req_proto, 'dashboard')
        self.assertEqual(resp.url, '/')

        # 3. Backslash URL attempt (\\evil.com) -> blocked
        req_slash = self.rf.post('/', {'next': r'\\evil.com'}, HTTP_HOST='testserver')
        resp = safe_redirect(req_slash, 'dashboard')
        self.assertEqual(resp.url, '/')

        # 4. External URL attempt (https://evil.com) -> blocked
        req_ext = self.rf.post('/', {'next': 'https://evil.com'}, HTTP_HOST='testserver')
        resp = safe_redirect(req_ext, 'dashboard')
        self.assertEqual(resp.url, '/')

        # 5. Safe fallback view name
        resp = safe_redirect(req, 'dashboard')
        self.assertEqual(resp.url, '/')

        # 6. HTTPS downgrade blocked when request is secure
        req_downgrade = self.rf.post(
            '/', {'next': 'http://testserver/tracker/'},
            HTTP_HOST='testserver', secure=True,
        )
        resp = safe_redirect(req_downgrade, 'dashboard')
        self.assertEqual(resp.url, '/')

        # 7. CRLF / control character injection blocked
        req_crlf = self.rf.post('/', {'next': '/tracker/\r\nSet-Cookie: evil=1'}, HTTP_HOST='testserver')
        resp = safe_redirect(req_crlf, 'dashboard')
        self.assertEqual(resp.url, '/')

        # 8. Untrusted bare view name in ?next= must NOT raise NoReverseMatch 500
        req_bare = self.rf.post('/', {'next': 'nonexistent_view_name_xyz'}, HTTP_HOST='testserver')
        resp = safe_redirect(req_bare, 'dashboard')
        self.assertEqual(resp.url, '/')

    def test_oauth_discovery_enforces_s256_pkce_only(self):
        resp = self.client.get('/.well-known/oauth-authorization-server')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data.get('code_challenge_methods_supported'), ['S256'])
        self.assertNotIn('plain', data.get('code_challenge_methods_supported', []))

    def test_media_url_not_served_unauthenticated_in_debug(self):
        from django.test import override_settings
        with override_settings(DEBUG=True):
            resp = self.client.get('/media/jewellery_photos/nonexistent.jpg')
            self.assertEqual(resp.status_code, 404)

    def test_feature_enabled_helper(self):
        # User without group returns True
        standalone_user = User(username="solo")
        self.assertTrue(feature_enabled(standalone_user, 'jewellery'))

        # User with group and config toggle
        group = AccountGroup.objects.create(name="ToggleGroup")
        user = User.objects.create_user(username="toggle_user", group=group)
        self.assertTrue(feature_enabled(user, 'jewellery'))

        group.config.feature_jewellery = False
        group.config.save()
        self.assertFalse(feature_enabled(user, 'jewellery'))


class ConcurrencyUtilitiesTests(TestCase):
    def test_parallel_map_execution(self):
        # Basic mapping
        squares = parallel_map(lambda x: x * x, [1, 2, 3, 4, 5], max_workers=3)
        self.assertEqual(squares, [1, 4, 9, 16, 25])

        # Empty items returns empty list
        self.assertEqual(parallel_map(lambda x: x, []), [])

    def test_parallel_map_exception_propagation(self):
        def _faulty(x):
            if x == 3:
                raise ValueError("Boom on 3")
            return x

        with self.assertRaises(ValueError):
            parallel_map(_faulty, [1, 2, 3, 4], max_workers=2)

    def test_django_safe_thread_pool_executor(self):
        def _worker(val):
            return val * 10

        with DjangoSafeThreadPoolExecutor(max_workers=2) as executor:
            fut = executor.submit(_worker, 7)
            self.assertEqual(fut.result(), 70)

    def test_safe_async_to_thread(self):
        def _sync_add(a, b):
            return a + b

        async def _test():
            return await safe_async_to_thread(_sync_add, 15, 25)

        res = asyncio.run(_test())
        self.assertEqual(res, 40)
