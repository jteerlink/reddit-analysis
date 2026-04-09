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
