import importlib
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture
def api_db(monkeypatch, tmp_path):
    db_path = tmp_path / "api.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
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
            """
        )
        conn.execute(
            """
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
            """
        )
        conn.execute(
            """
            CREATE TABLE preprocessed (
                id TEXT PRIMARY KEY,
                content_type TEXT NOT NULL,
                raw_text TEXT,
                clean_text TEXT,
                token_count INTEGER,
                is_filtered INTEGER NOT NULL DEFAULT 0,
                filter_reason TEXT,
                embedding_key TEXT,
                processed_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE sentiment_predictions (
                id TEXT PRIMARY KEY,
                content_type TEXT,
                label TEXT,
                confidence REAL,
                logits TEXT,
                model_version TEXT,
                predicted_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE topics (
                topic_id INTEGER PRIMARY KEY,
                keywords TEXT NOT NULL,
                doc_count INTEGER NOT NULL DEFAULT 0,
                coherence_score REAL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE topic_over_time (
                topic_id INTEGER NOT NULL,
                week_start TEXT NOT NULL,
                doc_count INTEGER NOT NULL DEFAULT 0,
                avg_sentiment REAL,
                PRIMARY KEY (topic_id, week_start)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE topic_assignments (
                id TEXT PRIMARY KEY,
                topic_id INTEGER NOT NULL,
                probability REAL,
                assigned_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE sentiment_daily (
                subreddit TEXT NOT NULL,
                date TEXT NOT NULL,
                mean_score REAL,
                pos_count INTEGER DEFAULT 0,
                neu_count INTEGER DEFAULT 0,
                neg_count INTEGER DEFAULT 0,
                PRIMARY KEY (subreddit, date)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE sentiment_moving_avg (
                subreddit TEXT NOT NULL,
                date TEXT NOT NULL,
                rolling_7d REAL,
                rolling_30d REAL,
                PRIMARY KEY (subreddit, date)
            )
            """
        )
        conn.execute(
            "CREATE TABLE change_points (subreddit TEXT, date TEXT, magnitude REAL)"
        )
        conn.execute(
            """
            CREATE TABLE sentiment_forecast (
                subreddit TEXT,
                date TEXT,
                yhat REAL,
                yhat_lower REAL,
                yhat_upper REAL
            )
            """
        )

        ts = datetime.now() - timedelta(days=1)
        conn.execute(
            "INSERT INTO posts (id, title, content, timestamp, subreddit, content_type) VALUES (?, ?, ?, ?, ?, ?)",
            ("p1", "Title", "Body", ts, "ChatGPT", "post"),
        )
        conn.execute(
            "INSERT INTO preprocessed (id, content_type, clean_text, is_filtered) VALUES (?, ?, ?, ?)",
            ("p1", "post", "good ai news", 0),
        )
        conn.execute(
            "INSERT INTO posts (id, title, content, timestamp, subreddit, content_type) VALUES (?, ?, ?, ?, ?, ?)",
            ("p2", "GPU", "RTX discussion", ts, "LocalLLaMA", "post"),
        )
        conn.execute(
            "INSERT INTO preprocessed (id, content_type, clean_text, is_filtered) VALUES (?, ?, ?, ?)",
            ("p2", "post", "gpu rtx", 0),
        )
        conn.execute(
            "INSERT INTO sentiment_predictions (id, content_type, label, confidence) VALUES (?, ?, ?, ?)",
            ("p1", "post", "positive", 0.91),
        )
        conn.execute(
            "INSERT INTO topics (topic_id, keywords, doc_count, coherence_score) VALUES (?, ?, ?, ?)",
            (1, '["ai"]', 10, 0.7),
        )
        conn.execute(
            "INSERT INTO topics (topic_id, keywords, doc_count, coherence_score) VALUES (?, ?, ?, ?)",
            (2, '["ai", "policy"]', 8, 0.65),
        )
        conn.execute(
            "INSERT INTO topics (topic_id, keywords, doc_count, coherence_score) VALUES (?, ?, ?, ?)",
            (3, '["crypto", "token"]', 4, 0.2),
        )
        conn.execute(
            "INSERT INTO topics (topic_id, keywords, doc_count, coherence_score) VALUES (?, ?, ?, ?)",
            (-1, '["outlier", "noise"]', 99, 0.0),
        )
        conn.execute(
            "INSERT INTO topic_assignments (id, topic_id, probability) VALUES (?, ?, ?)",
            ("p1", 1, 0.9),
        )
        conn.execute(
            "INSERT INTO topic_assignments (id, topic_id, probability) VALUES (?, ?, ?)",
            ("p2", 3, 0.8),
        )
        conn.execute(
            "INSERT INTO topic_over_time (topic_id, week_start, doc_count, avg_sentiment) VALUES (?, ?, ?, ?)",
            (1, "2026-04-27", 5, 0.4),
        )
        conn.execute(
            "INSERT INTO sentiment_daily (subreddit, date, mean_score, pos_count) VALUES (?, ?, ?, ?)",
            ("ChatGPT", ts.date().isoformat(), 0.8, 1),
        )
        conn.execute(
            "INSERT INTO sentiment_moving_avg (subreddit, date, rolling_7d, rolling_30d) VALUES (?, ?, ?, ?)",
            ("ChatGPT", ts.date().isoformat(), 0.8, 0.8),
        )
        conn.execute(
            "INSERT INTO change_points (subreddit, date, magnitude) VALUES (?, ?, ?)",
            ("ChatGPT", ts.date().isoformat(), 0.2),
        )
        conn.execute(
            "INSERT INTO sentiment_forecast (subreddit, date, yhat, yhat_lower, yhat_upper) VALUES (?, ?, ?, ?, ?)",
            ("ChatGPT", (ts.date() + timedelta(days=1)).isoformat(), 0.5, 0.1, 0.9),
        )

    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL_POOLED", raising=False)
    monkeypatch.setenv("REDDIT_DB_PATH", str(db_path))

    import src.db.connection as connection
    import src.api.db as db

    importlib.reload(connection)
    return importlib.reload(db)


def test_api_db_returns_expected_shapes(api_db):
    summary = api_db.get_collection_summary()
    assert summary["total_posts"] == 2
    assert summary["total_comments"] == 0

    assert api_db.get_sentiment_summary()[0]["label"] == "positive"
    assert api_db.get_daily_volume(("ChatGPT",), 30)[0]["subreddit"] == "ChatGPT"
    assert api_db.get_sentiment_daily(("ChatGPT",), 90)[0]["mean_score"] == 0.8
    assert api_db.get_change_points(("ChatGPT",))[0]["magnitude"] == 0.2
    assert api_db.get_forecast(("ChatGPT",))[0]["yhat"] == 0.5
    assert api_db.get_topics()[0]["topic_id"] == 1
    assert api_db.get_topic_over_time(1)[0]["doc_count"] == 5
    assert api_db.get_topic_heatmap(30)[0]["topic_id"] == 1
    assert api_db.get_known_subreddits() == ["ChatGPT", "LocalLLaMA"]


def test_api_db_topic_graph_is_deterministic_and_thresholded(api_db):
    graph = api_db.get_topic_graph(n=3, min_similarity=0.1)

    assert [node["topic_id"] for node in graph["nodes"]] == [1, 2, 3]
    assert all(node["topic_id"] != -1 for node in graph["nodes"])
    assert graph["edges"] == [
        {
            "source": 1,
            "target": 2,
            "similarity": graph["edges"][0]["similarity"],
            "shared_keywords": ["ai"],
        }
    ]
    assert graph["edges"][0]["similarity"] >= 0.1

    assert api_db.get_topic_graph(n=1, min_similarity=0.1)["nodes"] == [graph["nodes"][0]]
    assert api_db.get_topic_graph(n=3, min_similarity=0.95)["edges"] == []


def test_api_db_topic_graph_can_filter_by_subreddit(api_db):
    graph = api_db.get_topic_graph(n=10, min_similarity=0.0, subreddits=("ChatGPT",))

    assert [node["topic_id"] for node in graph["nodes"]] == [1]
    assert graph["nodes"][0]["doc_count"] == 1
    assert graph["edges"] == []


def test_api_db_deep_dive_filters(api_db):
    rows = api_db.get_deep_dive(
        keyword="ai",
        subreddits=("ChatGPT",),
        label_filter="positive",
        content_type_filter="post",
        limit=10,
        offset=0,
    )

    assert len(rows) == 1
    assert rows[0]["clean_text"] == "good ai news"


def test_api_db_empty_date_range_falls_back(monkeypatch, tmp_path):
    db_path = tmp_path / "empty.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE posts (id TEXT PRIMARY KEY, timestamp DATETIME)")

    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL_POOLED", raising=False)
    monkeypatch.setenv("REDDIT_DB_PATH", str(db_path))

    import src.db.connection as connection
    import src.api.db as db

    importlib.reload(connection)
    db = importlib.reload(db)

    result = db.get_date_range()
    assert set(result.keys()) == {"start", "end"}
