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


def test_activity_includes_operational_events_when_artifacts_are_empty():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    ensure_analysis_tables(conn)
    conn.executescript(
        """
        CREATE TABLE posts (id TEXT PRIMARY KEY, timestamp TEXT);
        CREATE TABLE sentiment_predictions (id TEXT PRIMARY KEY, predicted_at TEXT);
        CREATE TABLE sentiment_forecast (subreddit TEXT, date TEXT, yhat REAL);
        CREATE TABLE change_points (subreddit TEXT, date TEXT, magnitude REAL);
        """
    )
    conn.execute("INSERT INTO posts (id, timestamp) VALUES ('p1', '2026-05-01T00:00:00Z')")
    conn.execute("INSERT INTO sentiment_predictions (id, predicted_at) VALUES ('p1', '2026-05-02T00:00:00Z')")
    conn.execute("INSERT INTO sentiment_forecast (subreddit, date, yhat) VALUES ('ChatGPT', '2026-05-03', 0.2)")
    conn.commit()

    events = queries.activity(conn)

    assert {event["type"] for event in events} >= {"collection", "ml_run", "forecast"}
    assert all(event["state"] == "ready" for event in events)


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


def test_latest_brief_prefers_llm_and_preserves_section_metadata():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    ensure_analysis_tables(conn)
    deterministic = enqueue_artifact(
        conn,
        kind="analyst_brief",
        source_input_hash="deterministic",
        payload={"brief_id": "det", "headline": "Deterministic brief", "sections": []},
        provider="deterministic",
    )
    complete_artifact(conn, deterministic["artifact_id"], {"brief_id": "det", "headline": "Deterministic brief", "sections": []})
    llm = enqueue_artifact(
        conn,
        kind="analyst_brief_llm",
        source_input_hash="llm",
        payload={"brief_id": "llm", "headline": "LLM brief", "sections": []},
        provider="ollama",
        schema_version=2,
    )
    complete_artifact(
        conn,
        llm["artifact_id"],
        {
            "brief_id": "llm",
            "headline": "LLM brief",
            "sections": [
                {
                    "title": "Key Findings",
                    "body": "Body",
                    "evidence": [{"anchor_type": "event_id", "anchor_id": "1", "label": "Known event"}],
                }
            ],
        },
    )

    result = queries.latest_brief(conn)

    assert result["brief_id"] == "llm"
    assert result["provenance"]["label"] == "llm_artifact"
    assert result["sections"][0]["evidence"][0]["anchor_id"] == "1"


def test_latest_brief_skips_newer_queued_llm_artifact():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    ensure_analysis_tables(conn)
    succeeded = enqueue_artifact(
        conn,
        kind="analyst_brief_llm",
        source_input_hash="llm-success",
        payload={"brief_id": "llm-success", "headline": "Succeeded LLM brief", "sections": []},
        provider="ollama",
    )
    complete_artifact(conn, succeeded["artifact_id"], {"brief_id": "llm-success", "headline": "Succeeded LLM brief", "sections": []})
    queued = enqueue_artifact(
        conn,
        kind="analyst_brief_llm",
        source_input_hash="llm-queued",
        payload={"brief_id": "llm-queued", "headline": "Queued LLM brief", "sections": []},
        provider="ollama",
    )
    conn.execute(
        "UPDATE analysis_artifacts SET freshness_timestamp = '2099-01-01T00:00:00Z', updated_at = '2099-01-01T00:00:00Z' WHERE artifact_id = ?",
        (queued["artifact_id"],),
    )
    conn.commit()

    result = queries.latest_brief(conn)

    assert result["brief_id"] == "llm-success"
    assert result["provenance"]["label"] == "llm_artifact"


def test_briefs_returns_llm_and_deterministic_artifacts():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    ensure_analysis_tables(conn)
    deterministic = enqueue_artifact(
        conn,
        kind="analyst_brief",
        source_input_hash="deterministic",
        payload={"brief_id": "det", "headline": "Deterministic brief", "sections": []},
        provider="deterministic",
    )
    complete_artifact(conn, deterministic["artifact_id"], {"brief_id": "det", "headline": "Deterministic brief", "sections": []})
    llm = enqueue_artifact(
        conn,
        kind="analyst_brief_llm",
        source_input_hash="llm",
        payload={"brief_id": "llm", "headline": "LLM brief", "sections": []},
        provider="ollama",
    )
    complete_artifact(conn, llm["artifact_id"], {"brief_id": "llm", "headline": "LLM brief", "sections": []})

    result = queries.briefs(conn)

    assert {brief["brief_id"] for brief in result} == {"det", "llm"}
    assert {brief["provenance"]["label"] for brief in result} == {"deterministic_fallback", "llm_artifact"}


def test_briefs_prioritizes_succeeded_llm_over_newer_deterministic_artifact():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    ensure_analysis_tables(conn)
    llm = enqueue_artifact(
        conn,
        kind="analyst_brief_llm",
        source_input_hash="llm",
        payload={"brief_id": "llm", "headline": "LLM brief", "sections": []},
        provider="ollama",
    )
    complete_artifact(conn, llm["artifact_id"], {"brief_id": "llm", "headline": "LLM brief", "sections": []})
    deterministic = enqueue_artifact(
        conn,
        kind="analyst_brief",
        source_input_hash="deterministic",
        payload={"brief_id": "det", "headline": "Deterministic brief", "sections": []},
        provider="deterministic",
    )
    complete_artifact(conn, deterministic["artifact_id"], {"brief_id": "det", "headline": "Deterministic brief", "sections": []})
    conn.execute(
        "UPDATE analysis_artifacts SET freshness_timestamp = '2099-01-01T00:00:00Z', updated_at = '2099-01-01T00:00:00Z' WHERE artifact_id = ?",
        (deterministic["artifact_id"],),
    )
    conn.commit()

    result = queries.briefs(conn)

    assert [brief["brief_id"] for brief in result] == ["llm", "det"]
    assert result[0]["provenance"]["label"] == "llm_artifact"


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


def test_semantic_search_uses_vector_cache_when_available(tmp_path, monkeypatch):
    import sys
    import types

    import numpy as np

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
        ("p1", "post", "alpha aligned result", "p1"),
    )
    conn.execute(
        "INSERT INTO preprocessed (id, content_type, clean_text, embedding_key) VALUES (?, ?, ?, ?)",
        ("p2", "post", "orthogonal result", "p2"),
    )
    conn.execute("INSERT INTO sentiment_predictions (id, label, confidence) VALUES (?, ?, ?)", ("p1", "positive", 0.8))
    conn.execute("INSERT INTO sentiment_predictions (id, label, confidence) VALUES (?, ?, ?)", ("p2", "neutral", 0.5))
    conn.execute("INSERT INTO posts (id, subreddit, timestamp) VALUES (?, ?, ?)", ("p1", "LocalLLaMA", "2026-05-01"))
    conn.execute("INSERT INTO posts (id, subreddit, timestamp) VALUES (?, ?, ?)", ("p2", "ChatGPT", "2026-05-01"))
    conn.commit()

    models_dir = tmp_path / "models"
    models_dir.mkdir()
    (models_dir / "embeddings_index.json").write_text('{"p1": 0, "p2": 1}')
    np.save(models_dir / "embeddings_cache.npy", np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32))

    class FakeSentenceTransformer:
        def __init__(self, model_name):
            self.model_name = model_name

        def encode(self, texts, normalize_embeddings=True):
            return np.array([[1.0, 0.0]], dtype=np.float32)

    module = types.ModuleType("sentence_transformers")
    module.SentenceTransformer = FakeSentenceTransformer
    monkeypatch.setitem(sys.modules, "sentence_transformers", module)
    monkeypatch.chdir(tmp_path)

    results = queries.semantic_search(conn, "alpha", limit=2)

    assert [row["id"] for row in results] == ["p1", "p2"]
    assert results[0]["score"] > results[1]["score"]
    assert results[0]["provenance"]["algorithm"] == "minilm_cosine"


def test_embedding_map_stratifies_limited_points_by_parent_and_subreddit():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE embedding_2d (
            post_id TEXT PRIMARY KEY,
            x REAL NOT NULL,
            y REAL NOT NULL,
            cluster_id INTEGER NOT NULL
        );
        CREATE TABLE topic_assignments (
            id TEXT PRIMARY KEY,
            topic_id INTEGER
        );
        CREATE TABLE preprocessed (
            id TEXT PRIMARY KEY,
            clean_text TEXT
        );
        CREATE TABLE sentiment_predictions (
            id TEXT PRIMARY KEY,
            label TEXT
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
    records = [
        *[(f"local-{idx}", "LocalLLaMA") for idx in range(8)],
        ("infra-0", "nvidia"),
        ("infra-1", "nvidia"),
        ("openai-0", "OpenAI"),
        ("openai-1", "OpenAI"),
        ("claude-0", "ClaudeAI"),
        ("claude-1", "ClaudeAI"),
    ]
    for idx, (post_id, subreddit) in enumerate(records):
        conn.execute("INSERT INTO embedding_2d (post_id, x, y, cluster_id) VALUES (?, ?, ?, ?)", (post_id, idx, idx, 1))
        conn.execute("INSERT INTO topic_assignments (id, topic_id) VALUES (?, ?)", (post_id, idx % 3))
        conn.execute("INSERT INTO preprocessed (id, clean_text) VALUES (?, ?)", (post_id, f"{subreddit} sample"))
        conn.execute("INSERT INTO sentiment_predictions (id, label) VALUES (?, ?)", (post_id, "neutral"))
        conn.execute("INSERT INTO posts (id, subreddit, timestamp) VALUES (?, ?, ?)", (post_id, subreddit, "2026-05-01"))
    conn.commit()

    results = queries.embedding_map(conn, limit=4)

    assert [row["parent_id"] for row in results] == ["AI_INFRA", "ANTHROPIC", "OPENAI", "OPEN_SOURCE"]
    assert {row["subreddit"] for row in results} == {"nvidia", "ClaudeAI", "OpenAI", "LocalLLaMA"}
