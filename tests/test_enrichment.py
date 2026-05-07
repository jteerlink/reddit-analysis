"""
Tests for src/analysis/enrichment.py — LLM enrichment jobs.

All tests use a real SQLite in-memory database with the full analysis schema.
Ollama chat() is mocked to avoid network calls.
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.analysis.db import ensure_analysis_tables
from src.analysis.enrichment import (
    _select_model,
    enrich_analyst_brief,
    enrich_narrative_events,
    enrich_thread_analysis,
    enrich_topic_labels,
)
from src.analysis.ollama import OllamaConfig


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=OFF")
    return conn


def _seed_schema(conn):
    ensure_analysis_tables(conn)
    # Posts / comments / preprocessed / sentiment (minimal)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS posts (
            id TEXT PRIMARY KEY, title TEXT, subreddit TEXT,
            content TEXT, upvotes INTEGER, num_comments INTEGER,
            timestamp DATETIME, author TEXT, score INTEGER DEFAULT 0
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS comments (
            id TEXT PRIMARY KEY, post_id TEXT, content TEXT,
            subreddit TEXT, upvotes INTEGER, score INTEGER DEFAULT 0,
            timestamp DATETIME, author TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS preprocessed (
            id TEXT PRIMARY KEY, content_type TEXT,
            clean_text TEXT, is_filtered INTEGER DEFAULT 0, embedding_key TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sentiment_predictions (
            id TEXT PRIMARY KEY, content_type TEXT,
            label TEXT, confidence REAL
        )
    """)
    conn.commit()


@pytest.fixture
def conn():
    c = _make_conn()
    _seed_schema(c)
    yield c
    c.close()


@pytest.fixture
def local_config():
    return OllamaConfig(host="http://localhost:11434", api_key=None)


# ---------------------------------------------------------------------------
# _select_model
# ---------------------------------------------------------------------------


def test_select_model_returns_none_when_cloud_without_key(conn):
    config = OllamaConfig(host="https://ollama.com", api_key=None)
    result = _select_model(conn, config)
    assert result is None


def test_select_model_returns_none_when_discovery_fails(conn, local_config):
    with patch("src.analysis.enrichment.discover_models") as mock_disc:
        mock_disc.return_value = type("R", (), {"error": "timeout", "selected_model": None, "models": []})()
        result = _select_model(conn, local_config)
    assert result is None


def test_select_model_returns_model_on_success(conn, local_config):
    with patch("src.analysis.enrichment.discover_models") as mock_disc:
        mock_disc.return_value = type("R", (), {"error": None, "selected_model": "llama3", "models": []})()
        result = _select_model(conn, local_config)
    assert result == "llama3"


# ---------------------------------------------------------------------------
# enrich_thread_analysis
# ---------------------------------------------------------------------------


def test_enrich_thread_analysis_writes_artifact(conn, local_config):
    conn.execute("INSERT INTO posts (id, title, subreddit) VALUES ('p1', 'AI Discussion', 'MachineLearning')")
    conn.execute("INSERT INTO comments (id, post_id, content, score) VALUES ('c1', 'p1', 'Great post', 10)")
    conn.execute("INSERT INTO sentiment_predictions (id, label, confidence) VALUES ('c1', 'positive', 0.9)")
    conn.commit()

    with patch("src.analysis.enrichment._chat_safe", return_value="Commenters broadly agree AI is useful."):
        result = enrich_thread_analysis(conn, "p1", local_config, "llama3")

    assert result is not None
    assert "positions_summary" in result
    assert result["positions_summary"] == "Commenters broadly agree AI is useful."

    artifacts = conn.execute(
        "SELECT * FROM analysis_artifacts WHERE kind = 'thread_analysis' AND status = 'succeeded'"
    ).fetchall()
    assert len(artifacts) == 1
    payload = json.loads(artifacts[0]["payload"])
    assert payload["post_id"] == "p1"


def test_enrich_thread_analysis_idempotent(conn, local_config):
    conn.execute("INSERT INTO posts (id, title, subreddit) VALUES ('p2', 'Test Thread', 'python')")
    conn.commit()

    call_count = []

    def fake_chat_safe(config, model, messages, artifact_id, c):
        call_count.append(1)
        return "Summary text."

    with patch("src.analysis.enrichment._chat_safe", side_effect=fake_chat_safe):
        enrich_thread_analysis(conn, "p2", local_config, "llama3")
        enrich_thread_analysis(conn, "p2", local_config, "llama3")

    assert len(call_count) == 1


def test_enrich_thread_analysis_returns_none_for_missing_post(conn, local_config):
    result = enrich_thread_analysis(conn, "nonexistent", local_config, "llama3")
    assert result is None


# ---------------------------------------------------------------------------
# enrich_narrative_events
# ---------------------------------------------------------------------------


def test_enrich_narrative_events_enriches_events(conn, local_config):
    conn.execute("""
        INSERT INTO narrative_events
            (start_date, end_date, peak_date, sentiment_delta, dominant_subreddits, top_terms)
        VALUES ('2026-01-01', '2026-01-01', '2026-01-01', 0.4, '["python"]', '["ai", "tools"]')
    """)
    conn.commit()

    with patch("src.analysis.enrichment._chat_safe", return_value="AI Tools Surge\nPython community embraced new AI tools."):
        count = enrich_narrative_events(conn, local_config, "llama3", limit=5)

    assert count == 1
    artifacts = conn.execute(
        "SELECT * FROM analysis_artifacts WHERE kind = 'narrative_event_summary' AND status = 'succeeded'"
    ).fetchall()
    assert len(artifacts) == 1


def test_enrich_narrative_events_skips_already_enriched(conn, local_config):
    conn.execute("""
        INSERT INTO narrative_events
            (start_date, end_date, peak_date, sentiment_delta, dominant_subreddits, top_terms)
        VALUES ('2026-02-01', '2026-02-01', '2026-02-01', -0.3, '["news"]', '["economy"]')
    """)
    conn.commit()

    call_count = []

    def fake_chat(*args, **kwargs):
        call_count.append(1)
        return "Title\nSummary."

    with patch("src.analysis.enrichment._chat_safe", side_effect=fake_chat):
        enrich_narrative_events(conn, local_config, "llama3", limit=5)
        enrich_narrative_events(conn, local_config, "llama3", limit=5)

    assert len(call_count) == 1


def test_enrich_narrative_events_returns_zero_on_empty_table(conn, local_config):
    count = enrich_narrative_events(conn, local_config, "llama3", limit=5)
    assert count == 0


# ---------------------------------------------------------------------------
# enrich_analyst_brief
# ---------------------------------------------------------------------------


def test_enrich_analyst_brief_writes_artifact(conn, local_config):
    with patch(
        "src.analysis.enrichment._chat_safe",
        return_value="Reddit AI Trends Rise\n- AI tooling discussion up 40%\n- Python communities active\nOutlook: continued growth.",
    ):
        result = enrich_analyst_brief(conn, local_config, "llama3")

    assert result is not None
    assert "headline" in result
    assert result["headline"] == "Reddit AI Trends Rise"
    assert result["model_name"] == "llama3"

    artifacts = conn.execute(
        "SELECT * FROM analysis_artifacts WHERE kind = 'analyst_brief_llm' AND status = 'succeeded'"
    ).fetchall()
    assert len(artifacts) == 1


# ---------------------------------------------------------------------------
# enrich_topic_labels
# ---------------------------------------------------------------------------


def test_enrich_topic_labels_updates_labels(conn, local_config):
    conn.execute(
        "INSERT INTO cluster_labels (cluster_id, label, keywords, doc_count) VALUES (1, 'old label', '[\"ai\", \"tools\", \"model\"]', 500)"
    )
    conn.commit()

    with patch("src.analysis.enrichment._chat_safe", return_value="AI Tooling"):
        count = enrich_topic_labels(conn, local_config, "llama3", limit=10)

    assert count == 1
    row = conn.execute("SELECT label FROM cluster_labels WHERE cluster_id = 1").fetchone()
    assert row["label"] == "AI Tooling"


def test_enrich_topic_labels_skips_when_no_model(conn, local_config):
    conn.execute(
        "INSERT INTO cluster_labels (cluster_id, label, keywords, doc_count) VALUES (2, 'test', '[\"x\"]', 10)"
    )
    conn.commit()

    with patch("src.analysis.enrichment.discover_models") as mock_disc:
        mock_disc.return_value = type("R", (), {"error": "unavailable", "selected_model": None, "models": []})()
        model = _select_model(conn, local_config)

    assert model is None
