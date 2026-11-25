import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import migrate_to_neon, mirror_derived, pipeline_data
import src.ml.record_identity as record_identity


@pytest.fixture(autouse=True)
def _stub_record_identity_migration(monkeypatch):
    # migrate_record_identity's Postgres branch issues real Postgres DDL; it has
    # its own tests, so reconciliation tests stub it out to isolate _reconcile.
    monkeypatch.setattr(record_identity, "migrate_record_identity", lambda conn, commit=True: None)


class FakeCursor:
    def __init__(self):
        self.executed = []

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def execute(self, sql, params=None):
        self.executed.append((sql, params))


class FakeConnection:
    def __init__(self):
        self.cursors = []

    def cursor(self):
        cursor = FakeCursor()
        self.cursors.append(cursor)
        return cursor


def _frame(**columns):
    return pd.DataFrame(columns)


def test_reconcile_skips_inserts_when_nothing_changed(monkeypatch):
    conn = FakeConnection()
    frame = _frame(id=["a", "b"], value=["x", "y"])
    schema = {"posts": {"id": "text", "value": "text"}}
    monkeypatch.setattr(pipeline_data, "_target_schema", lambda c: schema)
    monkeypatch.setattr(pipeline_data, "_changed_rows", lambda c, table, f, s: ([], False))
    insert_calls = []
    monkeypatch.setattr(migrate_to_neon, "_insert_batch", lambda *a, **k: insert_calls.append(a[1]))
    replace_calls = []
    monkeypatch.setattr(mirror_derived, "replace_snapshot", lambda *a, **k: replace_calls.append(a))

    changed = pipeline_data._reconcile(conn, {"posts": frame}, None, 250, False)

    assert changed == []
    assert insert_calls == []
    assert replace_calls == []


def test_reconcile_inserts_and_verifies_changed_rows(monkeypatch):
    conn = FakeConnection()
    frame = _frame(id=["a", "b"], value=["x", "y"])
    schema = {"posts": {"id": "text", "value": "text"}}
    monkeypatch.setattr(pipeline_data, "_target_schema", lambda c: schema)
    calls = {"count": 0}

    def fake_changed_rows(c, table, f, s):
        calls["count"] += 1
        return ([0], False) if calls["count"] == 1 else ([], False)

    monkeypatch.setattr(pipeline_data, "_changed_rows", fake_changed_rows)
    insert_calls = []
    monkeypatch.setattr(migrate_to_neon, "_insert_batch", lambda *a, **k: insert_calls.append(a[1]))

    changed = pipeline_data._reconcile(conn, {"posts": frame}, None, 250, False)

    assert changed == ["posts"]
    assert insert_calls == ["posts"]


def test_reconcile_raises_when_verification_still_differs(monkeypatch):
    conn = FakeConnection()
    frame = _frame(id=["a"], value=["x"])
    schema = {"posts": {"id": "text", "value": "text"}}
    monkeypatch.setattr(pipeline_data, "_target_schema", lambda c: schema)
    monkeypatch.setattr(pipeline_data, "_changed_rows", lambda c, table, f, s: ([0], False))
    monkeypatch.setattr(migrate_to_neon, "_insert_batch", lambda *a, **k: None)

    with pytest.raises(ValueError, match="verification still differs"):
        pipeline_data._reconcile(conn, {"posts": frame}, None, 250, False)


def test_reconcile_replaces_derived_tables_together(monkeypatch):
    conn = FakeConnection()
    table_a, table_b = mirror_derived.DERIVED_TABLES[0], mirror_derived.DERIVED_TABLES[1]
    frame_a = _frame(id=["1"])
    frame_b = _frame(id=["2"])
    schema = {table_a: {"id": "text"}, table_b: {"id": "text"}}
    monkeypatch.setattr(pipeline_data, "_target_schema", lambda c: schema)
    calls = {"n": 0}

    def fake_changed_rows(c, table, f, s):
        calls["n"] += 1
        return ([], False) if calls["n"] > 2 else ([0], False)

    monkeypatch.setattr(pipeline_data, "_changed_rows", fake_changed_rows)
    replace_args = []
    monkeypatch.setattr(
        mirror_derived, "replace_snapshot",
        lambda conn_, frames, insert_batch, batch_size: replace_args.append(set(frames)),
    )

    changed = pipeline_data._reconcile(conn, {table_a: frame_a, table_b: frame_b}, None, 250, False)

    assert replace_args == [{table_a, table_b}]
    assert set(changed) == {table_a, table_b}


def test_reconcile_includes_pruned_tables_in_changed_list(monkeypatch):
    conn = FakeConnection()
    monkeypatch.setattr(pipeline_data, "_target_schema", lambda c: {})
    monkeypatch.setattr(pipeline_data, "prune_expired_records", lambda c, cutoff: {"posts": 3, "comments": 0})
    cutoff = datetime(2026, 1, 1, tzinfo=timezone.utc)

    changed = pipeline_data._reconcile(conn, {}, cutoff, 250, False)

    assert changed == ["posts"]


def test_reconcile_applies_schema_when_columns_missing(monkeypatch):
    conn = FakeConnection()
    frame = _frame(id=["a"], value=["x"])
    schema_calls = {"n": 0}

    def fake_schema(c):
        schema_calls["n"] += 1
        return {"posts": {}} if schema_calls["n"] == 1 else {"posts": {"id": "text", "value": "text"}}

    monkeypatch.setattr(pipeline_data, "_target_schema", fake_schema)
    monkeypatch.setattr(pipeline_data, "_changed_rows", lambda c, table, f, s: ([], False))

    changed = pipeline_data._reconcile(conn, {"posts": frame}, None, 250, True)

    assert changed == []
    assert schema_calls["n"] == 2
    applied = [sql for cur in conn.cursors for sql, _ in cur.executed]
    assert any("CREATE TABLE" in sql.upper() for sql in applied)


def test_reconcile_raises_when_schema_missing_columns_and_create_schema_false(monkeypatch):
    conn = FakeConnection()
    frame = _frame(id=["a"], value=["x"])
    monkeypatch.setattr(pipeline_data, "_target_schema", lambda c: {"posts": {}})

    with pytest.raises(ValueError, match="missing source columns"):
        pipeline_data._reconcile(conn, {"posts": frame}, None, 250, False)


class FakeOperationalError(Exception):
    pass


class FakeNeonConnection:
    def __init__(self):
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def cursor(self):
        return FakeCursor()

    def close(self):
        self.closed = True


class FakePsycopg2:
    OperationalError = FakeOperationalError

    def __init__(self, fail_times):
        self.fail_times = fail_times
        self.calls = 0

    def connect(self, dsn, connect_timeout=None):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise self.OperationalError("connection interrupted")
        return FakeNeonConnection()


def test_sync_neon_retries_once_after_an_interrupted_connection(tmp_path, monkeypatch):
    source = tmp_path / "source.db"
    sqlite3.connect(source).close()
    fake_psycopg2 = FakePsycopg2(fail_times=1)
    monkeypatch.setattr(migrate_to_neon, "_load_psycopg2", lambda: (fake_psycopg2, lambda v: v, None))
    monkeypatch.setattr(pipeline_data, "_reconcile", lambda conn, frames, cutoff, batch_size, create_schema: ["posts"])

    changed = pipeline_data.sync_neon(source, "dsn", None, 250, False)

    assert changed == ["posts"]
    assert fake_psycopg2.calls == 2


def test_sync_neon_reraises_after_a_second_consecutive_failure(tmp_path, monkeypatch):
    source = tmp_path / "source.db"
    sqlite3.connect(source).close()
    fake_psycopg2 = FakePsycopg2(fail_times=2)
    monkeypatch.setattr(migrate_to_neon, "_load_psycopg2", lambda: (fake_psycopg2, lambda v: v, None))
    monkeypatch.setattr(pipeline_data, "_reconcile", lambda conn, frames, cutoff, batch_size, create_schema: ["posts"])

    with pytest.raises(FakeOperationalError):
        pipeline_data.sync_neon(source, "dsn", None, 250, False)

    assert fake_psycopg2.calls == 2


def test_cutoff_action_prints_iso_timestamp(monkeypatch, capsys):
    monkeypatch.setattr(pipeline_data.sys, "argv", ["pipeline_data.py", "cutoff"])

    exit_code = pipeline_data.main()

    out = capsys.readouterr().out.strip()
    assert exit_code == 0
    assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+00:00$", out)


def test_prune_requires_db_and_cutoff(monkeypatch, capsys):
    monkeypatch.setattr(pipeline_data.sys, "argv", ["pipeline_data.py", "prune"])

    with pytest.raises(SystemExit) as exc:
        pipeline_data.main()

    assert exc.value.code == 2
    assert "--db is required" in capsys.readouterr().err


def test_prune_requires_timezone_aware_cutoff(monkeypatch, capsys):
    monkeypatch.setattr(
        pipeline_data.sys, "argv",
        ["pipeline_data.py", "prune", "--db", "x.db", "--cutoff", "2026-01-01T00:00:00"],
    )

    with pytest.raises(SystemExit) as exc:
        pipeline_data.main()

    assert exc.value.code == 2
    assert "must include a timezone" in capsys.readouterr().err


def test_sync_skips_when_database_url_targets_postgres(monkeypatch, capsys):
    monkeypatch.setattr(pipeline_data, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv("DATABASE_URL", "postgresql://example/db")
    monkeypatch.delenv("NEON_DATABASE_URL", raising=False)
    monkeypatch.setattr(pipeline_data.sys, "argv", ["pipeline_data.py", "sync", "--db", "ignored.db"])

    exit_code = pipeline_data.main()

    assert exit_code == 0
    assert "already using PostgreSQL" in capsys.readouterr().out


def test_sync_skips_when_neon_database_url_unset(monkeypatch, capsys):
    monkeypatch.setattr(pipeline_data, "load_dotenv", lambda *a, **k: None)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("NEON_DATABASE_URL", raising=False)
    monkeypatch.setattr(pipeline_data.sys, "argv", ["pipeline_data.py", "sync", "--db", "local.db"])

    exit_code = pipeline_data.main()

    assert exit_code == 0
    assert "NEON_DATABASE_URL is unset" in capsys.readouterr().out
