import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.analysis.db import complete_artifact, enqueue_artifact, ensure_analysis_tables
from src.analysis import queries


def test_activity_reports_missing_schema_state():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row

    events = queries.activity(conn)

    assert events[0]["state"] == "missing_schema"
    assert events[0]["provenance"]["label"] == "missing_config"


def test_activity_reports_unpopulated_state():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    ensure_analysis_tables(conn)

    events = queries.activity(conn)

    assert events[0]["state"] == "unpopulated"
    assert events[0]["provenance"]["producer_job"] == "run_analysis_backfill"


def test_freshness_tracks_latest_success_separately_from_latest_artifact():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    ensure_analysis_tables(conn)
    succeeded = enqueue_artifact(conn, kind="brief", source_input_hash="success", payload={})
    complete_artifact(conn, succeeded["artifact_id"], {"ok": True})
    failed = enqueue_artifact(conn, kind="brief", source_input_hash="failed", payload={})
    conn.execute(
        "UPDATE analysis_artifacts SET status = 'failed', freshness_timestamp = '2099-01-01T00:00:00Z' WHERE artifact_id = ?",
        (failed["artifact_id"],),
    )
    conn.commit()

    result = queries.freshness(conn)

    assert result["latest_artifact_at"] == "2099-01-01T00:00:00Z"
    assert result["latest_success_at"] != "2099-01-01T00:00:00Z"
    assert result["provenance"]["source"] == "analysis_artifacts"


def test_latest_brief_requires_succeeded_artifact():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    ensure_analysis_tables(conn)
    enqueue_artifact(conn, kind="analyst_brief", source_input_hash="queued", payload={"brief_id": "queued"})

    assert queries.latest_brief(conn) is None


def test_semantic_search_uses_nonconstant_lexical_fallback_scores():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE preprocessed (
            id TEXT PRIMARY KEY,
            content_type TEXT,
            clean_text TEXT,
            embedding_key TEXT
        );
        CREATE TABLE sentiment_predictions (
            id TEXT PRIMARY KEY,
            label TEXT,
            confidence REAL
        );
        CREATE TABLE posts (
            id TEXT PRIMARY KEY,
            subreddit TEXT,
            timestamp TEXT
        );
        CREATE TABLE comments (
            id TEXT PRIMARY KEY,
            subreddit TEXT,
            timestamp TEXT
        );
        """
    )
    conn.execute(
        "INSERT INTO preprocessed (id, content_type, clean_text, embedding_key) VALUES (?, ?, ?, ?)",
        ("p1", "post", "open source local model benchmark", "p1"),
    )
    conn.execute(
        "INSERT INTO preprocessed (id, content_type, clean_text, embedding_key) VALUES (?, ?, ?, ?)",
        ("p2", "post", "open thread about coffee", "p2"),
    )
    conn.execute("INSERT INTO sentiment_predictions (id, label, confidence) VALUES (?, ?, ?)", ("p1", "positive", 0.8))
    conn.execute("INSERT INTO sentiment_predictions (id, label, confidence) VALUES (?, ?, ?)", ("p2", "neutral", 0.5))
    conn.execute("INSERT INTO posts (id, subreddit, timestamp) VALUES (?, ?, ?)", ("p1", "LocalLLaMA", "2026-05-01"))
    conn.execute("INSERT INTO posts (id, subreddit, timestamp) VALUES (?, ?, ?)", ("p2", "ChatGPT", "2026-05-01"))
    conn.commit()

    results = queries.semantic_search(conn, "open model benchmark", limit=2)

    assert [row["id"] for row in results] == ["p1", "p2"]
    assert results[0]["score"] > results[1]["score"]
    assert results[0]["provenance"]["algorithm"] == "lexical_overlap_fallback"
