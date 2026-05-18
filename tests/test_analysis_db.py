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
from src.analysis.jobs import backfill_brief, backfill_embedding_2d, backfill_narrative_events


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


def test_enqueue_artifact_returns_existing_when_insert_hits_idempotency_race(monkeypatch):
    from src.analysis import db as analysis_db

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    ensure_analysis_tables(conn)

    real_execute = analysis_db.execute
    injected = False

    def execute_with_race(target_conn, sql, params=()):
        nonlocal injected
        if "INSERT INTO analysis_artifacts" in sql and not injected:
            injected = True
            real_execute(target_conn, sql, params)
            target_conn.commit()
            raise sqlite3.IntegrityError("UNIQUE constraint failed: analysis_artifacts.idempotency_key")
        return real_execute(target_conn, sql, params)

    monkeypatch.setattr(analysis_db, "execute", execute_with_race)

    artifact = enqueue_artifact(conn, kind="brief", source_input_hash="race", payload={"a": 1})

    assert artifact["kind"] == "brief"
    assert artifact["source_input_hash"] == "race"
    assert conn.execute("SELECT COUNT(*) FROM analysis_artifacts").fetchone()[0] == 1


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


def test_embedding_backfill_falls_back_to_reddit_id_cache_key(tmp_path, monkeypatch):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    ensure_analysis_tables(conn)
    conn.executescript(
        """
        CREATE TABLE topic_assignments (id TEXT PRIMARY KEY, topic_id INTEGER);
        CREATE TABLE preprocessed (id TEXT PRIMARY KEY, embedding_key TEXT);
        """
    )
    conn.execute("INSERT INTO topic_assignments (id, topic_id) VALUES (?, ?)", ("post-1", 3))
    conn.execute("INSERT INTO preprocessed (id, embedding_key) VALUES (?, ?)", ("post-1", "0"))
    conn.commit()

    models_dir = tmp_path / "models"
    models_dir.mkdir()
    (models_dir / "embeddings_index.json").write_text('{"post-1": 0}')
    import numpy as np

    np.save(models_dir / "embeddings_cache.npy", np.ones((1, 384), dtype=np.float32))
    monkeypatch.chdir(tmp_path)

    assert backfill_embedding_2d(conn) == 1
    assert conn.execute("SELECT COUNT(*) FROM embedding_2d").fetchone()[0] == 1


def test_embedding_backfill_projects_real_vectors_deterministically(tmp_path, monkeypatch):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    ensure_analysis_tables(conn)
    conn.executescript(
        """
        CREATE TABLE topic_assignments (id TEXT PRIMARY KEY, topic_id INTEGER);
        CREATE TABLE preprocessed (id TEXT PRIMARY KEY, embedding_key TEXT);
        """
    )
    for idx, topic_id in (("post-1", 1), ("post-2", 1), ("post-3", 2)):
        conn.execute("INSERT INTO topic_assignments (id, topic_id) VALUES (?, ?)", (idx, topic_id))
        conn.execute("INSERT INTO preprocessed (id, embedding_key) VALUES (?, ?)", (idx, idx))
    conn.commit()

    models_dir = tmp_path / "models"
    models_dir.mkdir()
    (models_dir / "embeddings_index.json").write_text('{"post-1": 0, "post-2": 1, "post-3": 2}')
    import numpy as np

    np.save(models_dir / "embeddings_cache.npy", np.array([[1.0, 0.0], [0.0, 1.0], [1.0, 1.0]], dtype=np.float32))
    monkeypatch.chdir(tmp_path)

    assert backfill_embedding_2d(conn) == 3
    first_coords = [
        tuple(row)
        for row in conn.execute("SELECT post_id, ROUND(x, 6), ROUND(y, 6), cluster_id FROM embedding_2d ORDER BY post_id")
    ]
    assert len({(row[1], row[2]) for row in first_coords}) > 1

    assert backfill_embedding_2d(conn) == 3
    second_coords = [
        tuple(row)
        for row in conn.execute("SELECT post_id, ROUND(x, 6), ROUND(y, 6), cluster_id FROM embedding_2d ORDER BY post_id")
    ]
    assert second_coords == first_coords


def test_embedding_backfill_stratifies_projection_source_by_parent_group(tmp_path, monkeypatch):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    ensure_analysis_tables(conn)
    conn.executescript(
        """
        CREATE TABLE topic_assignments (id TEXT PRIMARY KEY, topic_id INTEGER);
        CREATE TABLE preprocessed (id TEXT PRIMARY KEY, embedding_key TEXT);
        CREATE TABLE posts (
            id TEXT PRIMARY KEY,
            subreddit TEXT,
            subreddit_parent_id TEXT
        );
        """
    )
    records = [
        *[(f"local-{idx}", "LocalLLaMA", "OPEN_SOURCE") for idx in range(8)],
        ("openai-0", "OpenAI", "OPENAI"),
        ("claude-0", "ClaudeAI", "ANTHROPIC"),
        ("gemini-0", "GeminiAI", "GOOGLE"),
    ]
    for idx, (post_id, subreddit, parent_id) in enumerate(records):
        topic_id = -1 if parent_id == "GOOGLE" else idx % 2
        conn.execute("INSERT INTO topic_assignments (id, topic_id) VALUES (?, ?)", (post_id, topic_id))
        conn.execute("INSERT INTO preprocessed (id, embedding_key) VALUES (?, ?)", (post_id, post_id))
        conn.execute(
            "INSERT INTO posts (id, subreddit, subreddit_parent_id) VALUES (?, ?, ?)",
            (post_id, subreddit, parent_id),
        )
    conn.execute("INSERT INTO embedding_2d (post_id, x, y, cluster_id) VALUES ('stale', 0, 0, 0)")
    conn.commit()

    models_dir = tmp_path / "models"
    models_dir.mkdir()
    index = {post_id: idx for idx, (post_id, _subreddit, _parent_id) in enumerate(records)}
    (models_dir / "embeddings_index.json").write_text(json.dumps(index))
    import numpy as np

    np.save(models_dir / "embeddings_cache.npy", np.eye(len(records), dtype=np.float32))
    monkeypatch.chdir(tmp_path)

    assert backfill_embedding_2d(conn, limit=4) == 4

    parents = [
        row[0]
        for row in conn.execute(
            """
            SELECT p.subreddit_parent_id
            FROM embedding_2d e
            JOIN posts p ON e.post_id = p.id
            ORDER BY p.subreddit_parent_id
            """
        )
    ]
    assert parents == ["ANTHROPIC", "GOOGLE", "OPENAI", "OPEN_SOURCE"]
    assert conn.execute("SELECT COUNT(*) FROM embedding_2d WHERE post_id = 'stale'").fetchone()[0] == 0


def test_deterministic_brief_includes_evidence_sections():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    ensure_analysis_tables(conn)
    conn.execute(
        """
        CREATE TABLE sentiment_predictions (
            id TEXT PRIMARY KEY,
            label TEXT,
            confidence REAL
        )
        """
    )
    conn.execute(
        """
        INSERT INTO narrative_events (
            start_date, end_date, peak_date, peak_anomaly_score,
            sentiment_delta, dominant_subreddits, top_terms, top_post_ids, auto_label
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "2026-05-01",
            "2026-05-01",
            "2026-05-01",
            0.9,
            0.75,
            '["ChatGPT"]',
            '["model", "release"]',
            '["p1"]',
            "Positive sentiment shift in r/ChatGPT",
        ),
    )
    conn.execute(
        "INSERT INTO cluster_labels (cluster_id, label, keywords, doc_count) VALUES (?, ?, ?, ?)",
        (1, "model release", '["model", "release"]', 10),
    )
    conn.execute("INSERT INTO sentiment_predictions (id, label, confidence) VALUES (?, ?, ?)", ("p1", "positive", 0.55))
    conn.commit()

    assert backfill_brief(conn) == 1
    row = conn.execute("SELECT payload FROM analysis_artifacts WHERE kind = 'analyst_brief'").fetchone()
    payload = json.loads(row[0])

    titles = {section["title"] for section in payload["sections"]}
    assert {"Executive Summary", "Narrative Events", "Topic Labels", "Model Health", "Risks & Anomalies"} <= titles
    assert payload["sections"][1]["evidence"][0]["anchor_type"] == "event_id"
    assert "10 comments" in payload["sections"][2]["body"]
    assert "docs" not in payload["sections"][2]["body"]
