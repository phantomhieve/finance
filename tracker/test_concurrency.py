"""Unit tests for Vault concurrency primitives, database optimizations, and safe async execution."""
import asyncio
from unittest.mock import MagicMock, patch

from django.db import connection, connections
from django.test import TestCase, TransactionTestCase

from pftracker.concurrency import (
    DjangoSafeThreadPoolExecutor,
    close_thread_db_connections,
    parallel_map,
    safe_async_to_thread,
    safe_db_worker,
)
from pftracker.db_optimizations import configure_sqlite_connection
from tracker.models import AccountGroup, User


class ConcurrencySafetyTests(TransactionTestCase):
    def setUp(self):
        self.group = AccountGroup.objects.create(name="Concurrency Group")
        self.user = User.objects.create_user(
            username="concurrent_user",
            password="testpassword123",
            user_type="PRIMARY",
            group=self.group,
        )

    def test_safe_db_worker_in_thread(self):
        import concurrent.futures

        @safe_db_worker
        def worker_query():
            return User.objects.filter(username="concurrent_user").exists()

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(worker_query)
            result = future.result(timeout=5.0)

        self.assertTrue(result)

    def test_django_safe_thread_pool_executor(self):
        def db_task(idx):
            u = User.objects.get(username="concurrent_user")
            return f"{u.username}-{idx}"

        with DjangoSafeThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(db_task, i) for i in range(5)]
            results = [f.result(timeout=5.0) for f in futures]

        self.assertEqual(len(results), 5)
        self.assertTrue(all(r.startswith("concurrent_user-") for r in results))

    def test_parallel_map(self):
        def double_val(x):
            return x * 2

        mapped = parallel_map(double_val, [1, 2, 3, 4], max_workers=2)
        self.assertEqual(mapped, [2, 4, 6, 8])

        empty = parallel_map(double_val, [])
        self.assertEqual(empty, [])

    def test_safe_async_to_thread(self):
        async def run_async():
            def sync_fn():
                return User.objects.filter(username="concurrent_user").count()

            return await safe_async_to_thread(sync_fn)

        count = asyncio.run(run_async())
        self.assertEqual(count, 1)

    def test_close_thread_db_connections_swallows_errors(self):
        with patch.object(connections, "close_all", side_effect=Exception("DB close failure")):
            # Should not raise
            close_thread_db_connections()


class DBOptimizationsTests(TestCase):
    def test_sqlite_pragmas_applied(self):
        if connection.vendor == 'sqlite':
            cursor = connection.cursor()
            cursor.execute("PRAGMA busy_timeout;")
            busy_timeout = cursor.fetchone()[0]
            cursor.close()
            # Pragmas configured in configure_sqlite_connection set busy_timeout to 15000ms
            self.assertGreaterEqual(busy_timeout, 1000)

    def test_configure_sqlite_connection_signal_handler(self):
        mock_conn = MagicMock()
        mock_conn.vendor = 'sqlite'
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        configure_sqlite_connection(sender=self.__class__, connection=mock_conn)
        self.assertTrue(mock_cursor.execute.called)
        # Verify PRAGMA journal_mode = WAL was executed
        executed_cmds = [call.args[0] for call in mock_cursor.execute.call_args_list]
        self.assertTrue(any("WAL" in cmd for cmd in executed_cmds))


class ASGIMiddlewareTests(TestCase):
    def test_database_connection_lifecycle_middleware(self):
        from pftracker.asgi import DatabaseConnectionLifecycleMiddleware

        async def dummy_app(scope, receive, send):
            return {"status": "ok"}

        middleware = DatabaseConnectionLifecycleMiddleware(dummy_app)

        scope = {"type": "http", "method": "GET", "path": "/mcp"}
        receive = MagicMock()
        send = MagicMock()

        res = asyncio.run(middleware(scope, receive, send))
        self.assertEqual(res, {"status": "ok"})
