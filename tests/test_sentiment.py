"""
Tests for src/ml/sentiment.py — predict_batch, run_batch_inference, and LABEL2ID.

Integration tests use a temp SQLite DB with pre-populated preprocessed rows.
DistilBERT model is fully mocked to avoid requiring ML deps at test time.
"""

import json
import os
import sqlite3
import sys
import tempfile
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.ml.sentiment import LABEL2ID, ID2LABEL, predict_batch, run_batch_inference
from src.ml.db import get_connection


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def temp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    conn = sqlite3.connect(path)
    conn.execute("""
        CREATE TABLE posts (
            id TEXT PRIMARY KEY,
            title TEXT,
            content TEXT,
            upvotes INTEGER,
            timestamp DATETIME,
            subreddit TEXT,
            author TEXT,
            author_karma INTEGER,
            url TEXT,
            num_comments INTEGER,
            content_type TEXT DEFAULT 'post',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE comments (
            id TEXT PRIMARY KEY,
            parent_id TEXT,
            content TEXT,
            upvotes INTEGER,
            timestamp DATETIME,
            subreddit TEXT,
            author TEXT,
            author_karma INTEGER,
            post_id TEXT,
            content_type TEXT DEFAULT 'comment',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE preprocessed (
            id            TEXT PRIMARY KEY,
            content_type  TEXT NOT NULL,
            raw_text      TEXT,
            clean_text    TEXT,
            token_count   INTEGER,
            is_filtered   INTEGER NOT NULL DEFAULT 0,
            filter_reason TEXT,
            embedding_key TEXT,
            processed_at  DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # Three kept records
    conn.executemany(
        "INSERT INTO preprocessed (id, content_type, clean_text, is_filtered) VALUES (?, ?, ?, 0)",
        [
            ("p1", "post", "ai is transforming many industries in exciting ways"),
            ("p2", "post", "this model predicts outcomes with high accuracy"),
            ("p3", "comment", "language models keep improving each year"),
        ],
    )
    # One filtered record (should not appear in inference)
    conn.execute(
        "INSERT INTO preprocessed (id, content_type, clean_text, is_filtered, filter_reason) VALUES (?, ?, ?, 1, ?)",
        ("p4", "post", "short", "too_short"),
    )
    conn.commit()
    conn.close()

    yield path
    os.unlink(path)


# ---------------------------------------------------------------------------
# Label map
# ---------------------------------------------------------------------------


def test_label2id_keys():
    assert set(LABEL2ID.keys()) == {"positive", "neutral", "negative"}


def test_label2id_values_unique():
    assert len(set(LABEL2ID.values())) == 3


def test_id2label_inverse():
    for label, idx in LABEL2ID.items():
        assert ID2LABEL[idx] == label



# ---------------------------------------------------------------------------
# predict_batch — mocked model
# ---------------------------------------------------------------------------


def _make_predict_batch_patches(fake_logits_array):
    """
    Return context managers that patch DistilBert classes at the transformers
    module level (where predict_batch lazy-imports them from).
    """
    import torch

    n = len(fake_logits_array)

    mock_tok = MagicMock()
    mock_tok.return_value = {
        "input_ids": torch.zeros(n, 10, dtype=torch.long),
        "attention_mask": torch.ones(n, 10, dtype=torch.long),
    }
    mock_tok_cls = MagicMock()
    mock_tok_cls.from_pretrained.return_value = mock_tok

    mock_output = MagicMock()
    mock_output.logits = torch.tensor(fake_logits_array, dtype=torch.float32)
    mock_model = MagicMock()
    mock_model.return_value = mock_output
    mock_model_cls = MagicMock()
    mock_model_cls.from_pretrained.return_value = mock_model

    return (
        patch("transformers.DistilBertTokenizerFast", mock_tok_cls),
        patch("transformers.DistilBertForSequenceClassification", mock_model_cls),
    )


def test_predict_batch_output_length():
    fake_logits = [[0.1, 0.2, 2.0]] * 5
    p1, p2 = _make_predict_batch_patches(fake_logits)
    with p1, p2:
        results = predict_batch(["hello world"] * 5, model_dir="fake_dir", batch_size=10, device="cpu")
    assert len(results) == 5


def test_predict_batch_confidence_in_range():
    fake_logits = [[1.0, 0.5, -0.5]] * 3
    p1, p2 = _make_predict_batch_patches(fake_logits)
    with p1, p2:
        results = predict_batch(["test sentence"] * 3, model_dir="fake_dir", device="cpu")
    for r in results:
        assert 0.0 <= r["confidence"] <= 1.0


def test_predict_batch_label_valid():
    fake_logits = [
        [2.0, 0.1, 0.1],   # negative
        [0.1, 2.0, 0.1],   # neutral
        [0.1, 0.1, 2.0],   # positive
        [2.0, 0.1, 0.1],   # negative
    ]
    p1, p2 = _make_predict_batch_patches(fake_logits)
    with p1, p2:
        results = predict_batch(["text"] * 4, model_dir="fake_dir", device="cpu")
    valid_labels = {"positive", "neutral", "negative"}
    for r in results:
        assert r["label"] in valid_labels


def test_predict_batch_logits_length():
    fake_logits = [[0.1, 0.2, 2.0]] * 2
    p1, p2 = _make_predict_batch_patches(fake_logits)
    with p1, p2:
        results = predict_batch(["test"] * 2, model_dir="fake_dir", device="cpu")
    for r in results:
        assert len(r["logits"]) == 3


# ---------------------------------------------------------------------------
# run_batch_inference integration — mocked predict_batch
# ---------------------------------------------------------------------------


def test_run_batch_inference_integration(temp_db):
    fake_pred = {"label": "positive", "confidence": 0.95, "logits": [0.1, 0.1, 2.0]}

    with patch("src.ml.sentiment.predict_batch", return_value=[fake_pred] * 3):
        with tempfile.TemporaryDirectory() as model_dir:
            result = run_batch_inference(
                db_path=temp_db,
                model_dir=model_dir,
                batch_size=10,
                mlflow_tracking=False,
            )

    assert result["total_scored"] == 3   # p4 is filtered out
    assert result["positive_count"] == 3

    conn = get_connection(temp_db)
    rows = conn.execute("SELECT * FROM sentiment_predictions").fetchall()
    conn.close()

    assert len(rows) == 3
    ids = {r["id"] for r in rows}
    assert ids == {"p1", "p2", "p3"}

    for r in rows:
        assert r["label"] == "positive"
        assert r["confidence"] == pytest.approx(0.95)
        assert json.loads(r["logits"]) == [0.1, 0.1, 2.0]


def test_run_batch_inference_idempotent(temp_db):
    """Second run should score 0 new records."""
    fake_pred = {"label": "negative", "confidence": 0.88, "logits": [2.0, 0.1, 0.1]}

    with patch("src.ml.sentiment.predict_batch", return_value=[fake_pred] * 3):
        with tempfile.TemporaryDirectory() as model_dir:
            run_batch_inference(temp_db, model_dir, mlflow_tracking=False)
            result2 = run_batch_inference(temp_db, model_dir, mlflow_tracking=False)

    assert result2["total_scored"] == 0

    conn = get_connection(temp_db)
    count = conn.execute("SELECT COUNT(*) FROM sentiment_predictions").fetchone()[0]
    conn.close()
    assert count == 3
