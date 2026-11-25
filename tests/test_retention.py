import sqlite3
from datetime import datetime, timezone
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.reddit_api import retention


def test_retention_cutoff_rejects_naive_start_time():
    with pytest.raises(ValueError, match="timezone"):
        retention.retention_cutoff(datetime(2026, 1, 1))


def test_prune_expired_records_rejects_naive_cutoff():
    conn = sqlite3.connect(":memory:")
    with pytest.raises(ValueError, match="timezone"):
        retention.prune_expired_records(conn, datetime(2026, 1, 1))


def test_prune_expired_records_requires_posts_and_comments_tables():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE posts (id TEXT)")
    with pytest.raises(ValueError, match="Retention requires both posts and comments"):
        retention.prune_expired_records(conn, datetime(2026, 1, 1, tzinfo=timezone.utc))


class FakePostgresCursor:
    def __init__(self, conn):
        self._conn = conn
        self._last_sql = ""

    def execute(self, sql, params=()):
        self._conn.calls.append((sql, tuple(params)))
        self._last_sql = sql

    def __iter__(self):
        if "information_schema.tables" in self._last_sql:
            return iter([("posts",), ("comments",)])
        return iter([])

    @property
    def rowcount(self):
        if "DELETE FROM comments" in self._last_sql:
            return 2
        if "DELETE FROM posts" in self._last_sql:
            return 1
        return 0


class FakePostgresConnection:
    def __init__(self):
        self.calls = []

    def cursor(self):
        return FakePostgresCursor(self)


# Satisfies src.db.connection.is_postgres_connection without a real psycopg2 dependency.
FakePostgresConnection.__module__ = "psycopg2.extensions"


def test_prune_expired_records_postgres_path_uses_percent_s_placeholders():
    conn = FakePostgresConnection()
    cutoff = datetime(2026, 1, 1, tzinfo=timezone.utc)

    counts = retention.prune_expired_records(conn, cutoff)

    assert counts["posts"] == 1
    assert counts["comments"] == 2
    assert any(sql.count("%s") >= 1 and params for sql, params in conn.calls)
    assert not any("julianday" in sql or "?" in sql for sql, _ in conn.calls)
    assert any("content_type = %s" in sql and params == ("post",) for sql, params in conn.calls)
    assert any("content_type = %s" in sql and params == ("comment",) for sql, params in conn.calls)
