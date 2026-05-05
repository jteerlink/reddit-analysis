"""Shared database connection boundary for SQLite fallback and Neon Postgres."""

from __future__ import annotations

import atexit
import logging
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

try:  # pragma: no cover - exercised only when psycopg2 is installed
    import psycopg2
    from psycopg2.extras import DictCursor
    from psycopg2.pool import ThreadedConnectionPool
except ImportError:  # pragma: no cover - local SQLite tests do not require it
    psycopg2 = None
    DictCursor = None
    ThreadedConnectionPool = None


DATABASE_URL = os.environ.get("DATABASE_URL")
DATABASE_URL_POOLED = os.environ.get("DATABASE_URL_POOLED")
SQLITE_DB_PATH = os.environ.get("REDDIT_DB_PATH") or os.environ.get(
    "DATABASE_PATH", "historical_reddit_data.db"
)

_read_pool: Optional[Any] = None
_pooled_connection_ids: set[int] = set()


def get_backend() -> str:
    """Return the active backend name without opening a connection."""
    if DATABASE_URL and psycopg2 is not None:
        return "postgres"
    return "sqlite"


ACTIVE_BACKEND = get_backend()


def is_postgres() -> bool:
    return get_backend() == "postgres"


def is_postgres_connection(conn: Any) -> bool:
    return conn.__class__.__module__.startswith("psycopg2")


def paramstyle() -> str:
    return "%s" if is_postgres() else "?"


def placeholders(count: int) -> str:
    marker = paramstyle()
    return ",".join([marker] * count)


def false_literal() -> str:
    return "FALSE" if is_postgres() else "0"


def recent_interval_sql(column_sql: str, days: int, date_only: bool = False) -> str:
    days = int(days)
    if is_postgres():
        base = "CURRENT_DATE" if date_only else "NOW()"
        return f"{column_sql} >= {base} - INTERVAL '{days} days'"
    func = "DATE" if date_only else "datetime"
    return f"{column_sql} >= {func}('now', ?)"


def recent_interval_params(days: int) -> list[str]:
    return [] if is_postgres() else [f"-{int(days)} days"]


def sqlite_path() -> Path:
    path = Path(SQLITE_DB_PATH)
    if path.is_absolute():
        return path
    return Path.cwd() / path


def redact_target(target: str | Path | None = None) -> str:
    """Redact credentials and avoid leaking local absolute paths."""
    value = str(target or current_target())
    if value.startswith(("postgres://", "postgresql://")):
        parsed = urlparse(value)
        scheme = parsed.scheme
        host = parsed.hostname or "unknown-host"
        db_name = parsed.path.rsplit("/", 1)[-1] or "database"
        suffix = db_name[-4:] if len(db_name) > 4 else db_name
        return f"{scheme}://{host}/...{suffix}"
    return Path(value).name


def current_target(readonly: bool = True) -> str:
    if is_postgres():
        return (DATABASE_URL_POOLED if readonly else DATABASE_URL) or DATABASE_URL or ""
    return str(sqlite_path())


def _sqlite_connection(readonly: bool) -> sqlite3.Connection:
    db_path = sqlite_path()
    if readonly:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    else:
        conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    if not readonly:
        conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _postgres_pool() -> Any:
    global _read_pool
    if _read_pool is None:
        if psycopg2 is None or ThreadedConnectionPool is None:
            raise RuntimeError("psycopg2 is not installed")
        dsn = DATABASE_URL_POOLED or DATABASE_URL
        if not dsn:
            raise RuntimeError("DATABASE_URL is not configured")
        _read_pool = ThreadedConnectionPool(
            minconn=1, maxconn=10, dsn=dsn, cursor_factory=DictCursor
        )
    return _read_pool


def get_read_connection() -> Any:
    if is_postgres():
        conn = _postgres_pool().getconn()
        _pooled_connection_ids.add(id(conn))
        return conn
    return _sqlite_connection(readonly=True)


def get_write_connection() -> Any:
    if is_postgres():
        if psycopg2 is None:
            raise RuntimeError("psycopg2 is not installed")
        if not DATABASE_URL:
            raise RuntimeError("DATABASE_URL is not configured")
        return psycopg2.connect(DATABASE_URL, cursor_factory=DictCursor)
    return _sqlite_connection(readonly=False)


def release_connection(conn: Any) -> None:
    if conn is None:
        return
    conn_id = id(conn)
    if conn_id in _pooled_connection_ids and _read_pool is not None:
        _pooled_connection_ids.discard(conn_id)
        _read_pool.putconn(conn)
        return
    conn.close()


def execute(conn: Any, sql: str, params: tuple | list = ()):
    if is_postgres_connection(conn):
        cursor = conn.cursor()
        cursor.execute(sql, tuple(params))
        return cursor
    return conn.execute(sql, params)


@contextmanager
def connection(readonly: bool = True) -> Iterator[Any]:
    conn = get_read_connection() if readonly else get_write_connection()
    try:
        yield conn
    finally:
        release_connection(conn)


def database_reachable(readonly: bool = True) -> bool:
    try:
        with connection(readonly=readonly) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
        return True
    except Exception:
        logger.exception("Database reachability check failed")
        return False


def close_pools() -> None:
    global _read_pool
    if _read_pool is not None:
        _read_pool.closeall()
        _read_pool = None
        _pooled_connection_ids.clear()


atexit.register(close_pools)
