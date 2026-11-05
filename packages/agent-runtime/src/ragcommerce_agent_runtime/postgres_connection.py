"""Reuse PostgreSQL connections for the measured API/Worker hot path."""

from __future__ import annotations

import atexit
from contextlib import contextmanager
from contextvars import ContextVar
from threading import Lock

from psycopg_pool import ConnectionPool

_pools: dict[str, ConnectionPool] = {}
_lock = Lock()


_bound = ContextVar("bound_postgres_connection", default=None)


@contextmanager
def bind_connection(dsn, connection):
    token = _bound.set((dsn, connection))
    try:
        yield
    finally:
        _bound.reset(token)


@contextmanager
def connect(dsn: str):
    current = _bound.get()
    if current is not None and current[0] == dsn:
        yield current[1]
        return
    with _lock:
        if dsn not in _pools:
            pool = ConnectionPool(dsn, min_size=8, max_size=24, open=True)
            atexit.register(pool.close)
            pool.wait()
            _pools[dsn] = pool
        pool = _pools[dsn]
    # Same commit/rollback boundary as psycopg.connect's context manager.
    # Failed statements propagate; business requests are never retried here.
    with pool.connection() as connection:
        yield connection
