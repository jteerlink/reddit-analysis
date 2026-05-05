"""Database utilities for the ML pipeline with SQLite fallback and Neon support."""

import json
import os
import sqlite3
from typing import Generator, List, Tuple

from src.db.connection import get_write_connection, is_postgres_connection

try:
    import psycopg2
    from psycopg2.extras import DictCursor
except ImportError:  # pragma: no cover
    psycopg2 = None
    DictCursor = None


def get_connection(db_path: str):
    if db_path.startswith(("postgres://", "postgresql://")):
        if psycopg2 is None:
            raise RuntimeError("psycopg2-binary is required for PostgreSQL")
        return psycopg2.connect(db_path, cursor_factory=DictCursor)
    if os.environ.get("DATABASE_URL"):
        return get_write_connection()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _marker(conn) -> str:
    return "%s" if is_postgres_connection(conn) else "?"


def _false(conn) -> str:
    return "FALSE" if is_postgres_connection(conn) else "0"


def _recent_sql(conn, column: str, days: int) -> str:
    if is_postgres_connection(conn):
        return f"{column} >= NOW() - INTERVAL '{int(days)} days'"
    return f"{column} >= datetime('now', ?)"


def _recent_params(conn, days: int) -> tuple:
    return () if is_postgres_connection(conn) else (f"-{int(days)} days",)


def _json_value(value):
    if value is None:
        return None
    try:
        from psycopg2.extras import Json

        return Json(json.loads(value) if isinstance(value, str) else value)
    except ImportError:
        return value


def _execute(conn, sql: str, params: tuple = ()):
    if is_postgres_connection(conn):
        cursor = conn.cursor()
        cursor.execute(sql, params)
        return cursor
    return conn.execute(sql, params)


def _executemany(conn, sql: str, rows: List[Tuple]) -> None:
    if is_postgres_connection(conn):
        cursor = conn.cursor()
        cursor.executemany(sql, rows)
    else:
        conn.executemany(sql, rows)


def _upsert(conn, table: str, columns: list[str], conflict: list[str], update: list[str], rows: List[Tuple]) -> None:
    if not rows:
        return
    if is_postgres_connection(conn):
        marker = ", ".join([_marker(conn)] * len(columns))
        assignments = ", ".join(f"{col} = EXCLUDED.{col}" for col in update)
        sql = (
            f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({marker}) "
            f"ON CONFLICT ({', '.join(conflict)}) DO UPDATE SET {assignments}"
        )
    else:
        marker = ", ".join(["?"] * len(columns))
        sql = f"INSERT OR REPLACE INTO {table} ({', '.join(columns)}) VALUES ({marker})"
    _executemany(conn, sql, rows)
    conn.commit()


def ensure_preprocessed_table(conn) -> None:
    if is_postgres_connection(conn):
        _execute(conn, """
            CREATE TABLE IF NOT EXISTS preprocessed (
                id TEXT PRIMARY KEY,
                content_type TEXT NOT NULL,
                raw_text TEXT,
                clean_text TEXT,
                token_count INTEGER,
                is_filtered BOOLEAN NOT NULL DEFAULT FALSE,
                filter_reason TEXT,
                embedding_key TEXT,
                processed_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
    else:
        _execute(conn, """
            CREATE TABLE IF NOT EXISTS preprocessed (
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
        """)
    _execute(conn, "CREATE INDEX IF NOT EXISTS idx_preprocessed_filtered ON preprocessed(is_filtered)")
    conn.commit()


def iter_raw_records(conn, batch_size: int = 1000) -> Generator[List, None, None]:
    query = """
        SELECT id, title, content, 'post' AS content_type, author, subreddit
        FROM posts
        WHERE id NOT IN (SELECT id FROM preprocessed)
        UNION ALL
        SELECT id, NULL AS title, content, 'comment' AS content_type, author, subreddit
        FROM comments
        WHERE id NOT IN (SELECT id FROM preprocessed)
    """
    cursor = _execute(conn, query)
    while True:
        rows = cursor.fetchmany(batch_size)
        if not rows:
            break
        yield rows


def upsert_preprocessed(conn, rows: List[Tuple]) -> None:
    columns = [
        "id",
        "content_type",
        "raw_text",
        "clean_text",
        "token_count",
        "is_filtered",
        "filter_reason",
        "embedding_key",
    ]
    _upsert(conn, "preprocessed", columns, ["id"], columns[1:], rows)


def ensure_sentiment_table(conn) -> None:
    if is_postgres_connection(conn):
        _execute(conn, """
            CREATE TABLE IF NOT EXISTS sentiment_predictions (
                id TEXT PRIMARY KEY,
                content_type TEXT,
                label TEXT,
                confidence DOUBLE PRECISION,
                logits JSONB,
                model_version TEXT,
                predicted_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
    else:
        _execute(conn, """
            CREATE TABLE IF NOT EXISTS sentiment_predictions (
                id TEXT PRIMARY KEY,
                content_type TEXT,
                label TEXT,
                confidence REAL,
                logits TEXT,
                model_version TEXT,
                predicted_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
    _execute(conn, "CREATE INDEX IF NOT EXISTS idx_sentiment_label ON sentiment_predictions(label)")
    conn.commit()


def iter_unscored_records(conn, batch_size: int = 1000) -> Generator[List, None, None]:
    query = f"""
        SELECT id, content_type, clean_text
        FROM preprocessed
        WHERE is_filtered = {_false(conn)}
          AND clean_text IS NOT NULL
          AND clean_text != ''
          AND id NOT IN (SELECT id FROM sentiment_predictions)
    """
    cursor = _execute(conn, query)
    while True:
        rows = cursor.fetchmany(batch_size)
        if not rows:
            break
        yield rows


def upsert_sentiment(conn, rows: List[Tuple]) -> None:
    if is_postgres_connection(conn):
        rows = [
            (row[0], row[1], row[2], row[3], _json_value(row[4]), row[5])
            for row in rows
        ]
    columns = ["id", "content_type", "label", "confidence", "logits", "model_version"]
    _upsert(conn, "sentiment_predictions", columns, ["id"], columns[1:], rows)


def ensure_topics_tables(conn) -> None:
    if is_postgres_connection(conn):
        _execute(conn, """
            CREATE TABLE IF NOT EXISTS topics (
                topic_id INTEGER PRIMARY KEY,
                keywords TEXT NOT NULL,
                doc_count INTEGER NOT NULL DEFAULT 0,
                coherence_score DOUBLE PRECISION,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        _execute(conn, """
            CREATE TABLE IF NOT EXISTS topic_assignments (
                id TEXT PRIMARY KEY REFERENCES preprocessed(id),
                topic_id INTEGER NOT NULL,
                probability DOUBLE PRECISION,
                assigned_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        _execute(conn, """
            CREATE TABLE IF NOT EXISTS topic_over_time (
                topic_id INTEGER NOT NULL,
                week_start DATE NOT NULL,
                doc_count INTEGER NOT NULL DEFAULT 0,
                avg_sentiment DOUBLE PRECISION,
                PRIMARY KEY (topic_id, week_start)
            )
        """)
    else:
        _execute(conn, """
            CREATE TABLE IF NOT EXISTS topics (
                topic_id INTEGER PRIMARY KEY,
                keywords TEXT NOT NULL,
                doc_count INTEGER NOT NULL DEFAULT 0,
                coherence_score REAL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        _execute(conn, """
            CREATE TABLE IF NOT EXISTS topic_assignments (
                id TEXT PRIMARY KEY,
                topic_id INTEGER NOT NULL,
                probability REAL,
                assigned_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (id) REFERENCES preprocessed(id)
            )
        """)
        _execute(conn, """
            CREATE TABLE IF NOT EXISTS topic_over_time (
                topic_id INTEGER NOT NULL,
                week_start TEXT NOT NULL,
                doc_count INTEGER NOT NULL DEFAULT 0,
                avg_sentiment REAL,
                PRIMARY KEY (topic_id, week_start)
            )
        """)
    _execute(conn, "CREATE INDEX IF NOT EXISTS idx_topics_coherence ON topics(coherence_score)")
    _execute(conn, "CREATE INDEX IF NOT EXISTS idx_topic_assignments_topic ON topic_assignments(topic_id)")
    _execute(conn, "CREATE INDEX IF NOT EXISTS idx_tot_week ON topic_over_time(week_start)")
    conn.commit()


def iter_preprocessed_for_topics(conn, days: int = 90, batch_size: int = 1000) -> Generator[List, None, None]:
    query = f"""
        SELECT p.id, p.content_type, p.clean_text, p.embedding_key,
               COALESCE(posts.timestamp, comments.timestamp) AS source_timestamp
        FROM preprocessed p
        LEFT JOIN posts ON p.id = posts.id AND p.content_type = 'post'
        LEFT JOIN comments ON p.id = comments.id AND p.content_type = 'comment'
        WHERE p.is_filtered = {_false(conn)}
          AND p.clean_text IS NOT NULL
          AND p.clean_text != ''
          AND p.embedding_key IS NOT NULL
          AND {_recent_sql(conn, "p.processed_at", days)}
    """
    cursor = _execute(conn, query, _recent_params(conn, days))
    while True:
        rows = cursor.fetchmany(batch_size)
        if not rows:
            break
        yield rows


def upsert_topics(conn, rows: List[Tuple]) -> None:
    columns = ["topic_id", "keywords", "doc_count", "coherence_score"]
    _upsert(conn, "topics", columns, ["topic_id"], columns[1:], rows)


def upsert_topic_assignments(conn, rows: List[Tuple]) -> None:
    columns = ["id", "topic_id", "probability"]
    _upsert(conn, "topic_assignments", columns, ["id"], columns[1:], rows)


def upsert_topic_over_time(conn, rows: List[Tuple]) -> None:
    columns = ["topic_id", "week_start", "doc_count", "avg_sentiment"]
    _upsert(conn, "topic_over_time", columns, ["topic_id", "week_start"], columns[2:], rows)


def ensure_timeseries_tables(conn) -> None:
    if is_postgres_connection(conn):
        date_type = "DATE"
        real_type = "DOUBLE PRECISION"
    else:
        date_type = "TEXT"
        real_type = "REAL"
    _execute(conn, f"""
        CREATE TABLE IF NOT EXISTS sentiment_daily (
            subreddit TEXT NOT NULL,
            date {date_type} NOT NULL,
            mean_score {real_type},
            pos_count INTEGER NOT NULL DEFAULT 0,
            neu_count INTEGER NOT NULL DEFAULT 0,
            neg_count INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (subreddit, date)
        )
    """)
    _execute(conn, "CREATE INDEX IF NOT EXISTS idx_sd_date ON sentiment_daily(date)")
    _execute(conn, f"""
        CREATE TABLE IF NOT EXISTS sentiment_moving_avg (
            subreddit TEXT NOT NULL,
            date {date_type} NOT NULL,
            rolling_7d {real_type},
            rolling_30d {real_type},
            PRIMARY KEY (subreddit, date)
        )
    """)
    _execute(conn, f"""
        CREATE TABLE IF NOT EXISTS change_points (
            subreddit TEXT NOT NULL,
            date {date_type} NOT NULL,
            magnitude {real_type},
            PRIMARY KEY (subreddit, date)
        )
    """)
    _execute(conn, f"""
        CREATE TABLE IF NOT EXISTS sentiment_forecast (
            subreddit TEXT NOT NULL,
            date {date_type} NOT NULL,
            yhat {real_type},
            yhat_lower {real_type},
            yhat_upper {real_type},
            PRIMARY KEY (subreddit, date)
        )
    """)
    _execute(conn, f"""
        CREATE TABLE IF NOT EXISTS topic_sentiment_trends (
            topic_id INTEGER NOT NULL,
            date {date_type} NOT NULL,
            mean_sentiment {real_type},
            rolling_7d {real_type},
            PRIMARY KEY (topic_id, date)
        )
    """)
    _execute(conn, "CREATE INDEX IF NOT EXISTS idx_tst_date ON topic_sentiment_trends(date)")
    conn.commit()


def upsert_sentiment_daily(conn, rows: List[Tuple]) -> None:
    columns = ["subreddit", "date", "mean_score", "pos_count", "neu_count", "neg_count"]
    _upsert(conn, "sentiment_daily", columns, ["subreddit", "date"], columns[2:], rows)


def upsert_sentiment_moving_avg(conn, rows: List[Tuple]) -> None:
    columns = ["subreddit", "date", "rolling_7d", "rolling_30d"]
    _upsert(conn, "sentiment_moving_avg", columns, ["subreddit", "date"], columns[2:], rows)


def upsert_change_points(conn, rows: List[Tuple]) -> None:
    columns = ["subreddit", "date", "magnitude"]
    _upsert(conn, "change_points", columns, ["subreddit", "date"], columns[2:], rows)


def upsert_sentiment_forecast(conn, rows: List[Tuple]) -> None:
    columns = ["subreddit", "date", "yhat", "yhat_lower", "yhat_upper"]
    _upsert(conn, "sentiment_forecast", columns, ["subreddit", "date"], columns[2:], rows)


def upsert_topic_sentiment_trends(conn, rows: List[Tuple]) -> None:
    columns = ["topic_id", "date", "mean_sentiment", "rolling_7d"]
    _upsert(conn, "topic_sentiment_trends", columns, ["topic_id", "date"], columns[2:], rows)
