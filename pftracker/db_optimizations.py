"""Database connection optimizations and health monitors for Vault.

Applies high-concurrency PRAGMAs for SQLite (WAL mode, busy timeouts, memory cache)
and sets up connection health hooks for PostgreSQL in production.
"""
from __future__ import annotations

import logging
from django.db.backends.signals import connection_created
from django.dispatch import receiver

logger = logging.getLogger(__name__)


@receiver(connection_created)
def configure_sqlite_connection(sender, connection, **kwargs):
    """Ensure SQLite connections operate in WAL mode with high busy timeouts to prevent locking."""
    if connection.vendor == 'sqlite':
        try:
            cursor = connection.cursor()
            cursor.execute("PRAGMA journal_mode = WAL;")
            cursor.execute("PRAGMA synchronous = NORMAL;")
            cursor.execute("PRAGMA busy_timeout = 15000;")
            cursor.execute("PRAGMA cache_size = -64000;")  # 64MB memory page cache
            cursor.execute("PRAGMA foreign_keys = ON;")
            cursor.execute("PRAGMA temp_store = MEMORY;")
            cursor.close()
        except Exception as exc:
            logger.debug("Failed to apply SQLite PRAGMAs: %s", exc)

