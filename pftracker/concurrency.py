"""Concurrency and Thread-Safe Resource Management for Vault.

Provides custom executors and helpers that prevent database connection leaks,
ensure thread-local database cleanup, and support safe asynchronous offloading.
"""
from __future__ import annotations

import asyncio
import concurrent.futures
from functools import wraps
import logging
from typing import Any, Callable, Iterable, TypeVar

from django.db import close_old_connections, connections

logger = logging.getLogger(__name__)
T = TypeVar("T")
R = TypeVar("R")


def close_thread_db_connections():
    """Close all database connections bound to the current thread."""
    try:
        connections.close_all()
    except Exception as exc:
        logger.debug("Failed to close thread database connections: %s", exc)


def safe_db_worker(fn: Callable[..., R]) -> Callable[..., R]:
    """Decorator ensuring database connections are cleaned up before and after thread execution."""
    @wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> R:
        close_old_connections()
        try:
            return fn(*args, **kwargs)
        finally:
            close_thread_db_connections()
    return wrapper


class DjangoSafeThreadPoolExecutor(concurrent.futures.ThreadPoolExecutor):
    """ThreadPoolExecutor that automatically cleans up Django database connections
    on every worker thread to prevent connection leaks and descriptor exhaustion.
    """

    def submit(self, fn: Callable[..., R], *args: Any, **kwargs: Any) -> concurrent.futures.Future[R]:
        wrapped = safe_db_worker(fn)
        return super().submit(wrapped, *args, **kwargs)


async def safe_async_to_thread(fn: Callable[..., R], *args: Any, **kwargs: Any) -> R:
    """Run a synchronous callable in a separate thread while ensuring database connections are closed."""
    wrapped = safe_db_worker(fn)
    return await asyncio.to_thread(wrapped, *args, **kwargs)


def parallel_map(
    fn: Callable[[T], R],
    items: Iterable[T],
    max_workers: int = 4,
    timeout: float | None = None,
) -> list[R]:
    """Execute fn across items in parallel with bounded concurrency and safe database cleanup."""
    items_list = list(items)
    if not items_list:
        return []

    workers = min(max_workers, len(items_list))
    with DjangoSafeThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(fn, item) for item in items_list]
        return [f.result(timeout=timeout) for f in futures]

