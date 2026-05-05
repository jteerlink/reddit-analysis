#!/usr/bin/env python3
"""Detailed database statistics for SQLite fallback or Neon."""

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.db.connection import connection, get_backend, is_postgres, sqlite_path


def query_detailed_database_stats() -> dict:
    if get_backend() == "sqlite" and not sqlite_path().exists():
        raise FileNotFoundError(f"Database file not found: {sqlite_path()}")

    recent_clause = (
        "timestamp > NOW() - INTERVAL '7 days'"
        if is_postgres()
        else "timestamp > datetime('now', '-7 days')"
    )
    with connection(readonly=True) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM posts")
        post_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM comments")
        comment_count = cursor.fetchone()[0]
        cursor.execute("""
            SELECT subreddit, COUNT(*) AS post_count, AVG(upvotes) AS avg_upvotes
            FROM posts
            GROUP BY subreddit
            ORDER BY post_count DESC
        """)
        subreddit_stats = cursor.fetchall()
        cursor.execute("SELECT MIN(timestamp), MAX(timestamp) FROM posts")
        earliest_post, latest_post = cursor.fetchone()
        cursor.execute(f"SELECT COUNT(*) FROM posts WHERE {recent_clause}")
        recent_posts = cursor.fetchone()[0]
        cursor.execute(f"SELECT COUNT(*) FROM comments WHERE {recent_clause}")
        recent_comments = cursor.fetchone()[0]

    db_size_mb = sqlite_path().stat().st_size / (1024 * 1024) if get_backend() == "sqlite" else 0
    return {
        "post_count": post_count,
        "comment_count": comment_count,
        "subreddit_stats": subreddit_stats,
        "earliest_post": earliest_post,
        "latest_post": latest_post,
        "recent_posts": recent_posts,
        "recent_comments": recent_comments,
        "database_size_mb": round(db_size_mb, 2),
    }


def format_timestamp(timestamp_str):
    if not timestamp_str:
        return "N/A"
    try:
        dt = datetime.fromisoformat(str(timestamp_str).replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(timestamp_str)


def main():
    print("Detailed Historical Reddit Data Database Analysis")
    print("=" * 60)
    try:
        stats = query_detailed_database_stats()
        print(f"\nBasic Statistics:")
        print(f"   Backend: {get_backend()}")
        print(f"   Posts: {stats['post_count']:,}")
        print(f"   Comments: {stats['comment_count']:,}")
        print(f"   Total Items: {stats['post_count'] + stats['comment_count']:,}")
        if get_backend() == "sqlite":
            print(f"   Database Size: {stats['database_size_mb']} MB")
        print(f"\nData Time Range:")
        print(f"   Earliest Post: {format_timestamp(stats['earliest_post'])}")
        print(f"   Latest Post: {format_timestamp(stats['latest_post'])}")
        print(f"\nRecent Activity (Last 7 Days):")
        print(f"   New Posts: {stats['recent_posts']}")
        print(f"   New Comments: {stats['recent_comments']}")
        print(f"\nSubreddit Breakdown:")
        print(f"   {'Subreddit':<20} {'Posts':<8} {'Avg Upvotes':<12}")
        print(f"   {'-' * 20} {'-' * 8} {'-' * 12}")
        for subreddit, post_count, avg_upvotes in stats["subreddit_stats"]:
            avg_upvotes_str = f"{avg_upvotes:.1f}" if avg_upvotes else "N/A"
            print(f"   {subreddit:<20} {post_count:<8} {avg_upvotes_str:<12}")
    except FileNotFoundError as exc:
        print(f"Error: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
