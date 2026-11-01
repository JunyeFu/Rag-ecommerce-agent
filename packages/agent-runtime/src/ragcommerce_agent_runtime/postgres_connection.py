"""Reuse PostgreSQL connections for the measured API/Worker hot path."""

from __future__ import annotations

import atexit
from threading import Lock

from psycopg_pool import ConnectionPool

_pools: dict[str, ConnectionPool] = {}
_lock = Lock()


def connect(dsn: str):
    with _lock:
        if dsn not in _pools:
            pool = ConnectionPool(dsn, min_size=8, max_size=24, open=True)
            atexit.register(pool.close)
            pool.wait()
            _pools[dsn] = pool
        pool = _pools[dsn]
    # Same commit/rollback boundary as psycopg.connect's context manager.
    # Failed statements propagate; business requests are never retried here.
    return pool.connection()
