"""
Tests for src/ml/preprocessing.py — TextCleaner and EmbeddingGenerator.

Integration test uses a temp SQLite DB with fake posts to validate
the full run_preprocessing() pipeline without requiring GPU/MPS.
"""

import json
import os
import sqlite3
import sys
import tempfile
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.ml.preprocessing import TextCleaner, EmbeddingGenerator, run_preprocessing
from src.ml.db import get_connection, ensure_preprocessed_table


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
    conn.commit()
    conn.close()

    yield path
    os.unlink(path)


@pytest.fixture
def cleaner():
    return TextCleaner(lemmatize=False)


# ---------------------------------------------------------------------------
# TextCleaner — unit tests
# ---------------------------------------------------------------------------


def test_clean_strips_urls(cleaner):
    result = cleaner.clean("Check this out https://reddit.com/r/test and www.example.com")
    assert "https://" not in result
    assert "www." not in result
    assert "check this out" in result


def test_clean_strips_markdown_bold_italic(cleaner):
    result = cleaner.clean("This is **bold** and *italic* text")
    assert "**" not in result
    assert "*" not in result
    assert "bold" in result
    assert "italic" in result


def test_clean_strips_strikethrough(cleaner):
    result = cleaner.clean("~~removed text~~ kept text")
    assert "~~" not in result
    assert "removed text" in result
    assert "kept text" in result


def test_clean_strips_markdown_links(cleaner):
    result = cleaner.clean("[click here](https://example.com)")
    assert "click here" in result
    assert "https://" not in result
    assert "[" not in result


def test_clean_strips_block_quotes(cleaner):
    result = cleaner.clean("> quoted line\nnormal line")
    assert ">" not in result
    assert "normal line" in result


def test_clean_strips_inline_code(cleaner):
    result = cleaner.clean("Use `pip install` to install")
    assert "`" not in result
    assert "pip install" in result


def test_clean_strips_code_blocks(cleaner):
    result = cleaner.clean("```python\nprint('hello')\n```\nnormal text")
    assert "```" not in result
    assert "normal text" in result


def test_clean_lowercases(cleaner):
    result = cleaner.clean("UPPERCASE Text")
    assert result == result.lower()


def test_clean_collapses_whitespace(cleaner):
    result = cleaner.clean("too   many    spaces\n\n\nnewlines")
    assert "  " not in result
    assert "\n" not in result


def test_clean_empty_string(cleaner):
    assert cleaner.clean("") == ""
    assert cleaner.clean(None) == ""


# ---------------------------------------------------------------------------
# TextCleaner — is_bot
# ---------------------------------------------------------------------------


def test_is_bot_detects_automoderator(cleaner):
    assert TextCleaner.is_bot("AutoModerator") is True


def test_is_bot_detects_bot_suffix(cleaner):
    assert TextCleaner.is_bot("reddit_bot") is True
    assert TextCleaner.is_bot("news-bot") is True
    assert TextCleaner.is_bot("SomeBot") is True


def test_is_bot_detects_deleted(cleaner):
    assert TextCleaner.is_bot("[deleted]") is True
    assert TextCleaner.is_bot("[removed]") is True


def test_is_bot_passes_real_user(cleaner):
    assert TextCleaner.is_bot("jared_teerlink") is False
    assert TextCleaner.is_bot("regular_user123") is False


def test_is_bot_empty_author(cleaner):
    assert TextCleaner.is_bot("") is True
    assert TextCleaner.is_bot(None) is True


# ---------------------------------------------------------------------------
# TextCleaner — token_count / filtering threshold
# ---------------------------------------------------------------------------


def test_token_count_threshold(cleaner):
    short = "one two three four five six seven eight nine"  # 9 tokens
    assert TextCleaner.token_count(short) == 9


def test_token_count_ten_passes(cleaner):
    ten = "one two three four five six seven eight nine ten"  # 10 tokens
    assert TextCleaner.token_count(ten) == 10


# ---------------------------------------------------------------------------
# EmbeddingGenerator — device detection
# ---------------------------------------------------------------------------


def test_embedding_generator_device_is_valid():
    gen = EmbeddingGenerator.__new__(EmbeddingGenerator)
    from src.ml.preprocessing import _detect_device
    device = _detect_device()
    assert device in ("mps", "cuda", "cpu")


# ---------------------------------------------------------------------------
# Integration — run_preprocessing with mocked embeddings
# ---------------------------------------------------------------------------


def _insert_fake_posts(db_path: str):
    conn = sqlite3.connect(db_path)
    posts = [
        # (id, title, content, author)
        ("p1", "Great post about AI", "This is a really interesting discussion about artificial intelligence and machine learning.", "real_user"),
        ("p2", "Short", "Too short.", "real_user"),          # will be filtered (too_short)
        ("p3", "Bot post", "Some content here that is long enough to pass the token filter.", "AutoModerator"),  # filtered (bot)
        ("p4", "Another good post", "Discussing the latest developments in transformer architecture and its applications.", "user2"),
        ("p5", "Deleted post", "Content from a deleted account that has enough tokens to not be filtered by length.", "[deleted]"),  # filtered (bot)
    ]
    conn.executemany(
        "INSERT INTO posts (id, title, content, author, subreddit) VALUES (?, ?, ?, ?, 'testsubreddit')",
        posts,
    )
    conn.commit()
    conn.close()


def test_run_preprocessing_integration(temp_db):
    _insert_fake_posts(temp_db)

    fake_embedding = np.ones((1, 384), dtype=np.float32)

    with patch("src.ml.preprocessing.EmbeddingGenerator._get_model") as mock_model_loader:
        mock_model = MagicMock()
        mock_model.encode.return_value = fake_embedding
        mock_model_loader.return_value = mock_model

        with tempfile.TemporaryDirectory() as cache_dir:
            result = run_preprocessing(
                db_path=temp_db,
                cache_dir=cache_dir,
                batch_size=10,
                embed_batch_size=32,
                mlflow_tracking=False,
            )

    assert result["total"] == 5
    assert result["filtered"] == 3   # p2 (short), p3 (bot), p5 (bot/deleted)
    assert result["kept"] == 2       # p1, p4

    conn = get_connection(temp_db)
    rows = conn.execute("SELECT * FROM preprocessed").fetchall()
    conn.close()

    assert len(rows) == 5

    by_id = {r["id"]: r for r in rows}

    # Kept records have embedding_key set
    assert by_id["p1"]["is_filtered"] == 0
    assert by_id["p1"]["embedding_key"] is not None
    assert by_id["p4"]["is_filtered"] == 0
    assert by_id["p4"]["embedding_key"] is not None

    # Filtered records have no embedding_key
    assert by_id["p2"]["is_filtered"] == 1
    assert by_id["p2"]["filter_reason"] in ("too_short", "empty")
    assert by_id["p2"]["embedding_key"] is None

    assert by_id["p3"]["is_filtered"] == 1
    assert by_id["p3"]["filter_reason"] == "bot"

    assert by_id["p5"]["is_filtered"] == 1
    assert by_id["p5"]["filter_reason"] == "bot"


def test_run_preprocessing_idempotent(temp_db):
    """Running preprocessing twice should not create duplicate rows."""
    _insert_fake_posts(temp_db)

    fake_embedding = np.ones((1, 384), dtype=np.float32)

    with patch("src.ml.preprocessing.EmbeddingGenerator._get_model") as mock_model_loader:
        mock_model = MagicMock()
        mock_model.encode.return_value = fake_embedding
        mock_model_loader.return_value = mock_model

        with tempfile.TemporaryDirectory() as cache_dir:
            run_preprocessing(temp_db, cache_dir=cache_dir, mlflow_tracking=False)
            result2 = run_preprocessing(temp_db, cache_dir=cache_dir, mlflow_tracking=False)

    # Second run should process 0 new records
    assert result2["total"] == 0

    conn = get_connection(temp_db)
    count = conn.execute("SELECT COUNT(*) FROM preprocessed").fetchone()[0]
    conn.close()
    assert count == 5
