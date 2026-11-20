import sqlite3
import subprocess
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.migrate_to_neon import (
    EXCLUDED_TABLES,
    INSERT_PAGE_SIZE,
    MIGRATION_ORDER,
    _insert_batch,
    _insert_batch_resilient,
    _transform,
)


class FakeOperationalError(Exception):
    pass


class FakeCursor:
    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


class FakeConnection:
    def __init__(self, fail_when_rows_exceed=0):
        self.fail_when_rows_exceed = fail_when_rows_exceed
        self.closed = False
        self.commit_count = 0
        self.insert_sizes = []
        self.page_sizes = []

    def cursor(self):
        return FakeCursor(self)

    def close(self):
        self.closed = True

    def commit(self):
        self.commit_count += 1


def fake_execute_values(cursor, _sql, rows, page_size):
    cursor.connection.insert_sizes.append(len(rows))
    cursor.connection.page_sizes.append(page_size)
    if len(rows) > cursor.connection.fail_when_rows_exceed:
        raise FakeOperationalError("server closed the connection unexpectedly")


def test_migrate_to_neon_dry_run_reports_runtime_tables(tmp_path):
    source = tmp_path / "source.db"
    with sqlite3.connect(source) as conn:
        conn.execute("CREATE TABLE posts (id TEXT PRIMARY KEY)")
        conn.execute("CREATE TABLE comments (id TEXT PRIMARY KEY)")
        conn.execute("CREATE TABLE posts_other (id TEXT PRIMARY KEY)")
        conn.execute("CREATE TABLE embedding_2d (post_id TEXT PRIMARY KEY)")

    result = subprocess.run(
        [
            sys.executable,
            "scripts/migrate_to_neon.py",
            "--source",
            str(source),
            "--dry-run",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert "posts: 0 row(s)" in result.stdout
    assert "comments: 0 row(s)" in result.stdout
    assert "posts_other" in result.stdout
    assert "embedding_2d" in result.stdout
    assert "excluded from v1" in result.stdout


def test_analysis_tables_are_in_neon_migration_order():
    for table in [
        "analysis_artifacts",
        "embedding_2d",
        "cluster_labels",
        "narrative_events",
    ]:
        assert table in MIGRATION_ORDER
        assert table not in EXCLUDED_TABLES


def test_neon_schema_accepts_subreddit_parent_columns_from_sqlite():
    schema_sql = Path("scripts/neon_schema.sql").read_text()

    assert "subreddit_parent_id TEXT DEFAULT 'OTHER'" in schema_sql
    assert (
        "ALTER TABLE posts ADD COLUMN IF NOT EXISTS subreddit_parent_id" in schema_sql
    )
    assert (
        "ALTER TABLE comments ADD COLUMN IF NOT EXISTS subreddit_parent_id"
        in schema_sql
    )
    assert (
        "ALTER TABLE narrative_events ADD COLUMN IF NOT EXISTS llm_label" in schema_sql
    )
    assert (
        "ALTER TABLE narrative_events ADD COLUMN IF NOT EXISTS llm_summary"
        in schema_sql
    )


def test_transform_converts_missing_timestamps_to_none():
    df = pd.DataFrame(
        {
            "freshness_timestamp": [pd.NaT],
            "lease_expires_at": [""],
            "retry_after": [None],
            "created_at": ["2026-05-18T12:00:00Z"],
            "updated_at": [pd.NaT],
        }
    )

    transformed = _transform("analysis_artifacts", df)

    assert transformed.loc[0, "freshness_timestamp"] is None
    assert transformed.loc[0, "lease_expires_at"] is None
    assert transformed.loc[0, "retry_after"] is None
    assert transformed.loc[0, "updated_at"] is None


def test_migration_reconnects_and_splits_a_batch_when_neon_disconnects():
    initial_connection = FakeConnection(fail_when_rows_exceed=2)
    recovered_connection = FakeConnection(fail_when_rows_exceed=2)
    batch = pd.DataFrame({"id": ["a", "b", "c", "d"]})

    connection = _insert_batch_resilient(
        initial_connection,
        "posts",
        batch,
        fake_execute_values,
        lambda value: value,
        reconnect=lambda: recovered_connection,
        operational_error=FakeOperationalError,
    )

    assert connection is recovered_connection
    assert initial_connection.closed is True
    assert initial_connection.insert_sizes == [4]
    assert recovered_connection.insert_sizes == [2, 2]
    assert recovered_connection.page_sizes == [2, 2]
    assert recovered_connection.commit_count == 2


def test_insert_batch_caps_each_neon_statement_page_size():
    connection = FakeConnection(fail_when_rows_exceed=200)
    batch = pd.DataFrame({"id": [str(index) for index in range(INSERT_PAGE_SIZE + 1)]})

    _insert_batch(connection, "posts", batch, fake_execute_values, lambda value: value)

    assert connection.insert_sizes == [INSERT_PAGE_SIZE + 1]
    assert connection.page_sizes == [INSERT_PAGE_SIZE]
