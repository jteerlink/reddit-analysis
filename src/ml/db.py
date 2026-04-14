"""
ML Layer — Database Utilities

Thin SQLite helpers for the ML pipeline. Handles the `preprocessed` table
and incremental record iteration without touching the Phase 1 schema.
"""

import sqlite3
from typing import Generator, List, Tuple


def get_connection(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def ensure_preprocessed_table(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS preprocessed (
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
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_preprocessed_filtered ON preprocessed(is_filtered)"
    )
    conn.commit()


def iter_raw_records(
    conn: sqlite3.Connection, batch_size: int = 1000
) -> Generator[List[sqlite3.Row], None, None]:
    """
    Yield batches of unprocessed posts and comments.

    Pulls from both `posts` and `comments`, skipping any IDs already present
    in the `preprocessed` table.
    """
    query = """
        SELECT id, title, content, 'post' AS content_type, author, subreddit
        FROM posts
        WHERE id NOT IN (SELECT id FROM preprocessed)

        UNION ALL

        SELECT id, NULL AS title, content, 'comment' AS content_type, author, subreddit
        FROM comments
        WHERE id NOT IN (SELECT id FROM preprocessed)
    """
    cursor = conn.execute(query)
    while True:
        rows = cursor.fetchmany(batch_size)
        if not rows:
            break
        yield rows


def upsert_preprocessed(conn: sqlite3.Connection, rows: List[Tuple]) -> None:
    """
    Batch-insert rows into `preprocessed`.

    Each tuple: (id, content_type, raw_text, clean_text, token_count,
                  is_filtered, filter_reason, embedding_key)
    """
    conn.executemany(
        """
        INSERT OR REPLACE INTO preprocessed
            (id, content_type, raw_text, clean_text, token_count,
             is_filtered, filter_reason, embedding_key)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()


def ensure_sentiment_table(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sentiment_predictions (
            id            TEXT PRIMARY KEY,
            content_type  TEXT,
            label         TEXT,
            confidence    REAL,
            logits        TEXT,
            model_version TEXT,
            predicted_at  DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_sentiment_label ON sentiment_predictions(label)"
    )
    conn.commit()


def iter_unscored_records(
    conn: sqlite3.Connection, batch_size: int = 1000
) -> Generator[List[sqlite3.Row], None, None]:
    """Yield batches of preprocessed records not yet in sentiment_predictions."""
    query = """
        SELECT id, content_type, clean_text
        FROM preprocessed
        WHERE is_filtered = 0
          AND clean_text IS NOT NULL
          AND clean_text != ''
          AND id NOT IN (SELECT id FROM sentiment_predictions)
    """
    cursor = conn.execute(query)
    while True:
        rows = cursor.fetchmany(batch_size)
        if not rows:
            break
        yield rows


def upsert_sentiment(conn: sqlite3.Connection, rows: List[Tuple]) -> None:
    """
    Batch-insert rows into `sentiment_predictions`.

    Each tuple: (id, content_type, label, confidence, logits_json, model_version)
    """
    conn.executemany(
        """
        INSERT OR REPLACE INTO sentiment_predictions
            (id, content_type, label, confidence, logits, model_version)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Week 3 — Topic Modeling helpers
# ---------------------------------------------------------------------------


def ensure_topics_tables(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS topics (
            topic_id        INTEGER PRIMARY KEY,
            keywords        TEXT NOT NULL,
            doc_count       INTEGER NOT NULL DEFAULT 0,
            coherence_score REAL,
            created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_topics_coherence ON topics(coherence_score)"
    )
    conn.execute("""
        CREATE TABLE IF NOT EXISTS topic_assignments (
            id          TEXT PRIMARY KEY,
            topic_id    INTEGER NOT NULL,
            probability REAL,
            assigned_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (id) REFERENCES preprocessed(id)
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_topic_assignments_topic ON topic_assignments(topic_id)"
    )
    conn.execute("""
        CREATE TABLE IF NOT EXISTS topic_over_time (
            topic_id      INTEGER NOT NULL,
            week_start    TEXT NOT NULL,
            doc_count     INTEGER NOT NULL DEFAULT 0,
            avg_sentiment REAL,
            PRIMARY KEY (topic_id, week_start)
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_tot_week ON topic_over_time(week_start)"
    )
    conn.commit()


def iter_preprocessed_for_topics(
    conn: sqlite3.Connection, days: int = 90, batch_size: int = 1000
) -> Generator[List[sqlite3.Row], None, None]:
    """
    Yield batches of preprocessed records within the rolling window.

    JOINs back to posts/comments to retrieve the original Reddit timestamp
    (needed for weekly temporal bucketing).
    """
    query = """
        SELECT
            p.id,
            p.content_type,
            p.clean_text,
            p.embedding_key,
            COALESCE(posts.timestamp, comments.timestamp) AS source_timestamp
        FROM preprocessed p
        LEFT JOIN posts ON p.id = posts.id AND p.content_type = 'post'
        LEFT JOIN comments ON p.id = comments.id AND p.content_type = 'comment'
        WHERE p.is_filtered = 0
          AND p.clean_text IS NOT NULL
          AND p.clean_text != ''
          AND p.embedding_key IS NOT NULL
          AND p.processed_at >= datetime('now', ?)
    """
    cursor = conn.execute(query, (f"-{days} days",))
    while True:
        rows = cursor.fetchmany(batch_size)
        if not rows:
            break
        yield rows


def upsert_topics(conn: sqlite3.Connection, rows: List[Tuple]) -> None:
    """
    Batch-insert rows into `topics`.

    Each tuple: (topic_id, keywords_json, doc_count, coherence_score)
    """
    conn.executemany(
        """
        INSERT OR REPLACE INTO topics (topic_id, keywords, doc_count, coherence_score)
        VALUES (?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()


def upsert_topic_assignments(conn: sqlite3.Connection, rows: List[Tuple]) -> None:
    """
    Batch-insert rows into `topic_assignments`.

    Each tuple: (id, topic_id, probability)
    """
    conn.executemany(
        """
        INSERT OR REPLACE INTO topic_assignments (id, topic_id, probability)
        VALUES (?, ?, ?)
        """,
        rows,
    )
    conn.commit()


def upsert_topic_over_time(conn: sqlite3.Connection, rows: List[Tuple]) -> None:
    """
    Batch-insert rows into `topic_over_time`.

    Each tuple: (topic_id, week_start, doc_count, avg_sentiment)
    """
    conn.executemany(
        """
        INSERT OR REPLACE INTO topic_over_time (topic_id, week_start, doc_count, avg_sentiment)
        VALUES (?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Week 4 — Time Series helpers
# ---------------------------------------------------------------------------


def ensure_timeseries_tables(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sentiment_daily (
            subreddit   TEXT NOT NULL,
            date        TEXT NOT NULL,
            mean_score  REAL,
            pos_count   INTEGER NOT NULL DEFAULT 0,
            neu_count   INTEGER NOT NULL DEFAULT 0,
            neg_count   INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (subreddit, date)
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_sd_date ON sentiment_daily(date)"
    )
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sentiment_moving_avg (
            subreddit  TEXT NOT NULL,
            date       TEXT NOT NULL,
            rolling_7d REAL,
            rolling_30d REAL,
            PRIMARY KEY (subreddit, date)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS change_points (
            subreddit TEXT NOT NULL,
            date      TEXT NOT NULL,
            magnitude REAL,
            PRIMARY KEY (subreddit, date)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sentiment_forecast (
            subreddit   TEXT NOT NULL,
            date        TEXT NOT NULL,
            yhat        REAL,
            yhat_lower  REAL,
            yhat_upper  REAL,
            PRIMARY KEY (subreddit, date)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS topic_sentiment_trends (
            topic_id       INTEGER NOT NULL,
            date           TEXT NOT NULL,
            mean_sentiment REAL,
            rolling_7d     REAL,
            PRIMARY KEY (topic_id, date)
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_tst_date ON topic_sentiment_trends(date)"
    )
    conn.commit()


def upsert_sentiment_daily(conn: sqlite3.Connection, rows: List[Tuple]) -> None:
    """
    Batch-insert rows into `sentiment_daily`.

    Each tuple: (subreddit, date, mean_score, pos_count, neu_count, neg_count)
    """
    conn.executemany(
        """
        INSERT OR REPLACE INTO sentiment_daily
            (subreddit, date, mean_score, pos_count, neu_count, neg_count)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()


def upsert_sentiment_moving_avg(conn: sqlite3.Connection, rows: List[Tuple]) -> None:
    """
    Batch-insert rows into `sentiment_moving_avg`.

    Each tuple: (subreddit, date, rolling_7d, rolling_30d)
    """
    conn.executemany(
        """
        INSERT OR REPLACE INTO sentiment_moving_avg (subreddit, date, rolling_7d, rolling_30d)
        VALUES (?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()


def upsert_change_points(conn: sqlite3.Connection, rows: List[Tuple]) -> None:
    """
    Batch-insert rows into `change_points`.

    Each tuple: (subreddit, date, magnitude)
    """
    conn.executemany(
        """
        INSERT OR REPLACE INTO change_points (subreddit, date, magnitude)
        VALUES (?, ?, ?)
        """,
        rows,
    )
    conn.commit()


def upsert_sentiment_forecast(conn: sqlite3.Connection, rows: List[Tuple]) -> None:
    """
    Batch-insert rows into `sentiment_forecast`.

    Each tuple: (subreddit, date, yhat, yhat_lower, yhat_upper)
    """
    conn.executemany(
        """
        INSERT OR REPLACE INTO sentiment_forecast (subreddit, date, yhat, yhat_lower, yhat_upper)
        VALUES (?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()


def upsert_topic_sentiment_trends(conn: sqlite3.Connection, rows: List[Tuple]) -> None:
    """
    Batch-insert rows into `topic_sentiment_trends`.

    Each tuple: (topic_id, date, mean_sentiment, rolling_7d)
    """
    conn.executemany(
        """
        INSERT OR REPLACE INTO topic_sentiment_trends
            (topic_id, date, mean_sentiment, rolling_7d)
        VALUES (?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()
