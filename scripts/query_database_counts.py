#!/usr/bin/env python3
"""Query basic Reddit database counts from SQLite fallback or Neon."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.db.connection import connection, get_backend, sqlite_path


def query_database_counts() -> dict:
    if get_backend() == "sqlite" and not sqlite_path().exists():
        raise FileNotFoundError(f"Database file not found: {sqlite_path()}")

    with connection(readonly=True) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM posts")
        post_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM comments")
        comment_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(DISTINCT subreddit) FROM posts")
        unique_subreddits = cursor.fetchone()[0]
        cursor.execute("SELECT MIN(timestamp), MAX(timestamp) FROM posts")
        earliest_post, latest_post = cursor.fetchone()

    db_size_mb = sqlite_path().stat().st_size / (1024 * 1024) if get_backend() == "sqlite" else 0
    return {
        "post_count": post_count,
        "comment_count": comment_count,
        "unique_subreddits": unique_subreddits,
        "earliest_post": earliest_post or "No posts",
        "latest_post": latest_post or "No posts",
        "database_size_mb": round(db_size_mb, 2),
    }


def main():
    print("Querying historical Reddit data database...")
    print("=" * 50)
    try:
        stats = query_database_counts()
        print("Database Statistics:")
        print(f"   Backend: {get_backend()}")
        print(f"   Posts: {stats['post_count']:,}")
        print(f"   Comments: {stats['comment_count']:,}")
        print(f"   Unique Subreddits: {stats['unique_subreddits']}")
        if get_backend() == "sqlite":
            print(f"   Database Size: {stats['database_size_mb']} MB")
        print(f"   Date Range: {stats['earliest_post']} to {stats['latest_post']}")
        print(f"\nTotal Items: {stats['post_count'] + stats['comment_count']:,}")
    except FileNotFoundError as exc:
        print(f"Error: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
