"""Tests for src/ml/topics.py and the Week 3 db helpers."""

import json
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from src.ml.db import (
    ensure_topics_tables,
    get_connection,
    iter_preprocessed_for_topics,
    upsert_topic_assignments,
    upsert_topic_over_time,
    upsert_topics,
)
from src.ml.topics import (
    EmbeddingCache,
    TopicModeler,
    run_topic_modeling,
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _create_schema(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS posts (
            id TEXT PRIMARY KEY, title TEXT, content TEXT, upvotes INTEGER,
            timestamp DATETIME, subreddit TEXT, author TEXT, author_karma INTEGER,
            url TEXT, num_comments INTEGER, content_type TEXT DEFAULT 'post',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS comments (
            id TEXT PRIMARY KEY, parent_id TEXT, content TEXT NOT NULL,
            upvotes INTEGER, timestamp DATETIME, subreddit TEXT, author TEXT,
            author_karma INTEGER, post_id TEXT, content_type TEXT DEFAULT 'comment',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS preprocessed (
            id TEXT PRIMARY KEY, content_type TEXT NOT NULL,
            raw_text TEXT, clean_text TEXT, token_count INTEGER,
            is_filtered INTEGER NOT NULL DEFAULT 0, filter_reason TEXT,
            embedding_key TEXT, processed_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sentiment_predictions (
            id TEXT PRIMARY KEY, content_type TEXT, label TEXT,
            confidence REAL, logits TEXT, model_version TEXT,
            predicted_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def temp_db(tmp_path):
    db_path = str(tmp_path / "test.db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    _create_schema(conn)

    week1 = "2026-03-30 10:00:00"
    week2 = "2026-04-06 10:00:00"

    for i in range(8):
        ts = week1 if i < 4 else week2
        text = "machine learning artificial intelligence neural network model"
        conn.execute(
            "INSERT INTO posts (id, content, timestamp, subreddit, author) "
            "VALUES (?, ?, ?, 'r/ML', 'user1')",
            (f"post_{i}", text, ts),
        )
        conn.execute(
            "INSERT INTO preprocessed "
            "(id, content_type, clean_text, is_filtered, embedding_key, processed_at) "
            "VALUES (?, 'post', ?, 0, ?, datetime('now'))",
            (f"post_{i}", text, f"key_{i}"),
        )
        label = "positive" if i % 2 == 0 else "negative"
        conn.execute(
            "INSERT INTO sentiment_predictions (id, content_type, label, confidence) "
            "VALUES (?, 'post', ?, 0.85)",
            (f"post_{i}", label),
        )

    # 2 filtered records (no posts row needed — they'll be excluded by WHERE)
    for i in range(8, 10):
        conn.execute(
            "INSERT INTO preprocessed (id, content_type, is_filtered, filter_reason) "
            "VALUES (?, 'post', 1, 'too_short')",
            (f"post_{i}",),
        )

    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def temp_cache_dir(tmp_path):
    cache_dir = str(tmp_path / "models")
    Path(cache_dir).mkdir()
    # Row i has all values equal to float(i) — makes subset values verifiable
    arr = np.tile(np.arange(8, dtype=np.float32).reshape(-1, 1), (1, 384))
    np.save(str(Path(cache_dir) / "embeddings_cache.npy"), arr)
    index = {f"key_{i}": i for i in range(8)}
    with open(Path(cache_dir) / "embeddings_index.json", "w") as f:
        json.dump(index, f)
    return cache_dir


@pytest.fixture
def mem_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    _create_schema(conn)
    return conn


# ---------------------------------------------------------------------------
# EmbeddingCache unit tests
# ---------------------------------------------------------------------------

def test_embedding_cache_load(temp_cache_dir):
    cache = EmbeddingCache(temp_cache_dir)
    arr, idx = cache.load()
    assert arr.shape == (8, 384)
    assert len(idx) == 8
    assert idx["key_0"] == 0
    assert idx["key_7"] == 7


def test_embedding_cache_load_is_cached(temp_cache_dir):
    cache = EmbeddingCache(temp_cache_dir)
    arr1, _ = cache.load()
    arr2, _ = cache.load()
    assert arr1 is arr2  # same object — no re-load


def test_embedding_cache_get_subset(temp_cache_dir):
    cache = EmbeddingCache(temp_cache_dir)
    subset = cache.get_subset(["key_0", "key_2", "key_5"])
    assert subset.shape == (3, 384)
    assert float(subset[0, 0]) == pytest.approx(0.0)
    assert float(subset[1, 0]) == pytest.approx(2.0)
    assert float(subset[2, 0]) == pytest.approx(5.0)


def test_embedding_cache_get_subset_missing_key(temp_cache_dir):
    cache = EmbeddingCache(temp_cache_dir)
    subset = cache.get_subset(["key_0", "no_such_key", "key_1"])
    assert subset.shape == (2, 384)  # missing key skipped gracefully


def test_embedding_cache_missing_file_raises(tmp_path):
    cache = EmbeddingCache(str(tmp_path))
    with pytest.raises(FileNotFoundError):
        cache.load()


# ---------------------------------------------------------------------------
# TopicModeler unit tests
# ---------------------------------------------------------------------------

def test_compute_coherence_returns_float_in_range():
    modeler = TopicModeler()
    mock_model = MagicMock()
    mock_model.get_topic.return_value = [
        ("machine", 0.9), ("learning", 0.8), ("neural", 0.7),
        ("model", 0.6), ("ai", 0.5),
    ]
    modeler._model = mock_model
    modeler._doc_topics = [0] * 20
    docs = ["machine learning neural model ai training data"] * 20
    score = modeler.compute_coherence(0, docs)
    assert isinstance(score, float)
    assert 0.0 <= score <= 1.0


def test_compute_coherence_no_topic_docs_returns_zero():
    modeler = TopicModeler()
    mock_model = MagicMock()
    mock_model.get_topic.return_value = [("word", 0.9), ("other", 0.8)]
    modeler._model = mock_model
    # All docs assigned to topic 1, none to topic 0
    modeler._doc_topics = [1] * 10
    score = modeler.compute_coherence(0, ["some text"] * 10)
    assert score == 0.0


def test_check_gate_passes():
    modeler = TopicModeler()
    scores = [0.65] * 25
    passed, report = modeler.check_gate(scores)
    assert passed is True
    assert report["n_coherent_topics"] == 25
    assert report["mean_coherence"] == pytest.approx(0.65)


def test_check_gate_fails_too_few_topics():
    modeler = TopicModeler()
    scores = [0.65] * 15
    passed, report = modeler.check_gate(scores)
    assert passed is False
    assert report["n_coherent_topics"] == 15


def test_check_gate_fails_low_coherence():
    modeler = TopicModeler()
    scores = [0.65] * 10 + [0.30] * 15
    passed, report = modeler.check_gate(scores)
    assert passed is False
    assert report["n_coherent_topics"] == 10


def test_check_gate_empty_scores():
    modeler = TopicModeler()
    passed, report = modeler.check_gate([])
    assert passed is False
    assert report["n_coherent_topics"] == 0


def test_train_raises_without_model():
    modeler = TopicModeler()
    with pytest.raises(RuntimeError):
        modeler.train(["doc"], np.zeros((1, 384)))


# ---------------------------------------------------------------------------
# DB helper tests
# ---------------------------------------------------------------------------

def test_ensure_topics_tables_creates_tables(mem_conn):
    ensure_topics_tables(mem_conn)
    tables = {
        row[0]
        for row in mem_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    assert "topics" in tables
    assert "topic_assignments" in tables
    assert "topic_over_time" in tables


def test_ensure_topics_tables_idempotent(mem_conn):
    ensure_topics_tables(mem_conn)
    ensure_topics_tables(mem_conn)  # must not raise


def test_iter_preprocessed_for_topics_excludes_filtered(temp_db):
    conn = get_connection(temp_db)
    ensure_topics_tables(conn)
    rows = []
    for batch in iter_preprocessed_for_topics(conn, days=365):
        rows.extend(batch)
    conn.close()
    assert len(rows) == 8  # 2 filtered records excluded


def test_iter_preprocessed_for_topics_respects_days_window(tmp_path):
    db_path = str(tmp_path / "window.db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    _create_schema(conn)
    conn.execute(
        "INSERT INTO preprocessed (id, content_type, clean_text, is_filtered, "
        "embedding_key, processed_at) VALUES ('old', 'post', 'old text', 0, "
        "'key_old', datetime('now', '-200 days'))"
    )
    conn.execute(
        "INSERT INTO preprocessed (id, content_type, clean_text, is_filtered, "
        "embedding_key, processed_at) VALUES ('new', 'post', 'new text', 0, "
        "'key_new', datetime('now', '-1 days'))"
    )
    conn.commit()
    ensure_topics_tables(conn)
    rows = []
    for batch in iter_preprocessed_for_topics(conn, days=90):
        rows.extend(batch)
    conn.close()
    assert len(rows) == 1
    assert rows[0]["id"] == "new"


def test_upsert_topics(mem_conn):
    ensure_topics_tables(mem_conn)
    rows = [
        (0, '["machine", "learning"]', 100, 0.72),
        (1, '["neural", "network"]', 85, 0.61),
        (-1, "[]", 12, None),
    ]
    upsert_topics(mem_conn, rows)
    count = mem_conn.execute("SELECT COUNT(*) FROM topics").fetchone()[0]
    assert count == 3


def test_upsert_topic_assignments(mem_conn):
    ensure_topics_tables(mem_conn)
    for i in range(5):
        mem_conn.execute(
            "INSERT INTO preprocessed (id, content_type, is_filtered) VALUES (?, 'post', 0)",
            (f"doc_{i}",),
        )
    mem_conn.commit()
    rows = [(f"doc_{i}", i % 2, 0.8) for i in range(5)]
    upsert_topic_assignments(mem_conn, rows)
    count = mem_conn.execute("SELECT COUNT(*) FROM topic_assignments").fetchone()[0]
    assert count == 5


def test_upsert_topic_over_time(mem_conn):
    ensure_topics_tables(mem_conn)
    rows = [
        (0, "2026-03-30", 40, 0.3),
        (0, "2026-04-06", 35, 0.5),
        (1, "2026-03-30", 20, -0.1),
        (1, "2026-04-06", 18, 0.2),
    ]
    upsert_topic_over_time(mem_conn, rows)
    count = mem_conn.execute("SELECT COUNT(*) FROM topic_over_time").fetchone()[0]
    assert count == 4


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------

def _fake_topic_info():
    return [
        {"topic_id": 0, "keywords": ["machine", "learning"], "doc_count": 4},
        {"topic_id": 1, "keywords": ["neural", "network"], "doc_count": 4},
    ]


def test_run_topic_modeling_integration(temp_db, temp_cache_dir):
    fake_assignments = [0] * 4 + [1] * 4
    fake_probs = np.array([0.85] * 8, dtype=np.float32)

    with (
        patch("src.ml.topics.TopicModeler._build_model", return_value=MagicMock()),
        patch("src.ml.topics.TopicModeler.train", return_value=(fake_assignments, fake_probs)),
        patch("src.ml.topics.TopicModeler.get_topic_info", return_value=_fake_topic_info()),
        patch("src.ml.topics.TopicModeler.compute_coherence", return_value=0.65),
    ):
        result = run_topic_modeling(
            db_path=temp_db,
            cache_dir=temp_cache_dir,
            days=365,
            mlflow_tracking=False,
        )

    assert result["total_docs"] == 8
    assert result["n_topics"] == 2
    assert result["gate_passed"] is False  # only 2 topics < 20 required

    conn = sqlite3.connect(temp_db)
    assert conn.execute("SELECT COUNT(*) FROM topics").fetchone()[0] == 2
    assert conn.execute("SELECT COUNT(*) FROM topic_assignments").fetchone()[0] == 8
    assert conn.execute("SELECT COUNT(*) FROM topic_over_time").fetchone()[0] > 0
    conn.close()


def test_run_topic_modeling_idempotent(temp_db, temp_cache_dir):
    fake_assignments = [0] * 4 + [1] * 4
    fake_probs = np.array([0.85] * 8, dtype=np.float32)
    kwargs = dict(db_path=temp_db, cache_dir=temp_cache_dir, days=365, mlflow_tracking=False)

    with (
        patch("src.ml.topics.TopicModeler._build_model", return_value=MagicMock()),
        patch("src.ml.topics.TopicModeler.train", return_value=(fake_assignments, fake_probs)),
        patch("src.ml.topics.TopicModeler.get_topic_info", return_value=_fake_topic_info()),
        patch("src.ml.topics.TopicModeler.compute_coherence", return_value=0.65),
    ):
        run_topic_modeling(**kwargs)
        run_topic_modeling(**kwargs)

    conn = sqlite3.connect(temp_db)
    assert conn.execute("SELECT COUNT(*) FROM topics").fetchone()[0] == 2
    assert conn.execute("SELECT COUNT(*) FROM topic_assignments").fetchone()[0] == 8
    conn.close()


def test_run_topic_modeling_excludes_filtered(temp_db, temp_cache_dir):
    fake_assignments = [0] * 4 + [1] * 4
    fake_probs = np.array([0.85] * 8, dtype=np.float32)

    with (
        patch("src.ml.topics.TopicModeler._build_model", return_value=MagicMock()),
        patch("src.ml.topics.TopicModeler.train", return_value=(fake_assignments, fake_probs)),
        patch("src.ml.topics.TopicModeler.get_topic_info", return_value=_fake_topic_info()),
        patch("src.ml.topics.TopicModeler.compute_coherence", return_value=0.65),
    ):
        result = run_topic_modeling(
            db_path=temp_db,
            cache_dir=temp_cache_dir,
            days=365,
            mlflow_tracking=False,
        )

    assert result["total_docs"] == 8  # 2 filtered records not included
