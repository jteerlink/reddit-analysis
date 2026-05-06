import sqlite3
import sys
from pathlib import Path
import json

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.analysis.db import (
    claim_next_artifact,
    complete_artifact,
    enqueue_artifact,
    ensure_analysis_tables,
    fail_artifact,
    list_artifacts,
)
from src.analysis.jobs import backfill_narrative_events


def test_analysis_schema_and_backfill_lifecycle_are_idempotent():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    ensure_analysis_tables(conn)
    ensure_analysis_tables(conn)

    first = enqueue_artifact(conn, kind="brief", source_input_hash="abc", payload={"a": 1})
    second = enqueue_artifact(conn, kind="brief", source_input_hash="abc", payload={"a": 1})

    assert first["artifact_id"] == second["artifact_id"]
    assert first["status"] == "queued"

    claimed = claim_next_artifact(conn, worker_id="worker-1", lease_seconds=600)
    assert claimed is not None
    assert claimed["status"] == "running"
    assert claimed["lease_owner"] == "worker-1"

    completed = complete_artifact(conn, claimed["artifact_id"], {"done": True})
    assert completed["status"] == "succeeded"
    assert completed["checksum"]

    rows = list_artifacts(conn, kind="brief")
    assert len(rows) == 1
    assert rows[0]["status"] == "succeeded"


def test_analysis_lifecycle_retries_transient_failures_until_terminal():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    ensure_analysis_tables(conn)
    artifact = enqueue_artifact(
        conn,
        kind="model_summary",
        source_input_hash="retry-me",
        payload={},
        max_attempts=1,
    )
    claimed = claim_next_artifact(conn, worker_id="worker-1")
    failed = fail_artifact(conn, claimed["artifact_id"], "timeout", "provider timed out")

    assert failed["artifact_id"] == artifact["artifact_id"]
    assert failed["status"] == "failed"
    assert failed["error_category"] == "timeout"


def test_claim_next_artifact_does_not_double_claim_running_item():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    ensure_analysis_tables(conn)
    enqueue_artifact(conn, kind="brief", source_input_hash="claim-once", payload={})

    first = claim_next_artifact(conn, worker_id="worker-1")
    second = claim_next_artifact(conn, worker_id="worker-2")

    assert first is not None
    assert second is None


def test_narrative_backfill_is_idempotent_for_rows_and_artifacts():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    ensure_analysis_tables(conn)
    conn.execute("CREATE TABLE change_points (subreddit TEXT, date TEXT, magnitude REAL)")
    conn.execute(
        "INSERT INTO change_points (subreddit, date, magnitude) VALUES (?, ?, ?)",
        ("ChatGPT", "2026-05-01", 0.75),
    )
    conn.commit()

    assert backfill_narrative_events(conn) == 1
    payload_before = conn.execute(
        "SELECT payload FROM analysis_artifacts WHERE kind = 'narrative_events'"
    ).fetchone()[0]
    assert backfill_narrative_events(conn) == 0
    payload_after = conn.execute(
        "SELECT payload FROM analysis_artifacts WHERE kind = 'narrative_events'"
    ).fetchone()[0]

    assert conn.execute("SELECT COUNT(*) FROM narrative_events").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM analysis_artifacts WHERE kind = 'narrative_events'").fetchone()[0] == 1
    assert json.loads(payload_before)["event_count"] == 1
    assert payload_after == payload_before


def test_narrative_aggregate_refreshes_when_event_set_changes():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    ensure_analysis_tables(conn)
    conn.execute("CREATE TABLE change_points (subreddit TEXT, date TEXT, magnitude REAL)")
    conn.execute(
        "INSERT INTO change_points (subreddit, date, magnitude) VALUES (?, ?, ?)",
        ("ChatGPT", "2026-05-01", 0.75),
    )
    conn.commit()

    assert backfill_narrative_events(conn) == 1
    conn.execute(
        "INSERT INTO change_points (subreddit, date, magnitude) VALUES (?, ?, ?)",
        ("OpenAI", "2026-05-02", -0.8),
    )
    conn.commit()

    assert backfill_narrative_events(conn) == 1
    aggregate_payloads = [
        json.loads(row[0])
        for row in conn.execute(
            "SELECT payload FROM analysis_artifacts WHERE kind = 'narrative_events' ORDER BY created_at"
        ).fetchall()
    ]

    assert conn.execute("SELECT COUNT(*) FROM narrative_events").fetchone()[0] == 2
    assert len(aggregate_payloads) == 2
    assert aggregate_payloads[-1]["event_count"] == 2
