"""Apply the rolling post and comment retention policy."""

from calendar import monthrange
from datetime import datetime, timezone
from typing import Any

from src.db.connection import execute, is_postgres_connection


def retention_cutoff(started_at: datetime) -> datetime:
    if started_at.tzinfo is None:
        raise ValueError("Pipeline start time must have a timezone")
    instant = started_at.astimezone(timezone.utc).replace(microsecond=0)
    year, month = divmod(instant.year * 12 + instant.month - 1 - 18, 12)
    month += 1
    return instant.replace(year=year, month=month, day=min(instant.day, monthrange(year, month)[1]))


def prune_expired_records(conn: Any, cutoff: datetime) -> dict[str, int]:
    """Delete expired records inside the caller's transaction and retain undated records."""
    if cutoff.tzinfo is None:
        raise ValueError("Retention cutoff must have a timezone")
    postgres = is_postgres_connection(conn)
    marker = "%s" if postgres else "?"
    cutoff = cutoff.astimezone(timezone.utc)
    before_cutoff = "timestamp < %s" if postgres else "julianday(timestamp) < julianday(?)"
    timestamp = cutoff if postgres else cutoff.isoformat()
    if postgres:
        tables = {row[0] for row in execute(conn, """
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = current_schema() AND table_type = 'BASE TABLE'
        """)}
    else:
        tables = {row[0] for row in execute(conn, "SELECT name FROM sqlite_master WHERE type='table'")}
    if not {"posts", "comments"}.issubset(tables):
        raise ValueError("Retention requires both posts and comments tables")

    counts = {}
    execute(conn, "CREATE TEMP TABLE expired_reddit_records (content_type TEXT, id TEXT, PRIMARY KEY (content_type, id))")
    for posts, comments in (("posts", "comments"), ("posts_other", "comments_other")):
        if posts in tables:
            execute(conn, f"""
                INSERT INTO expired_reddit_records SELECT 'post', id FROM {posts}
                WHERE id IS NOT NULL AND {before_cutoff}
            """, (timestamp,))
        if comments in tables:
            execute(conn, f"""
                INSERT INTO expired_reddit_records SELECT 'comment', id FROM {comments}
                WHERE id IS NOT NULL AND ({before_cutoff} OR
                    post_id IN (SELECT id FROM expired_reddit_records WHERE content_type = 'post'))
            """, (timestamp,))
        if posts == "posts":
            for table, key in (("topic_assignments", "id"), ("embedding_2d", "post_id"),
                               ("sentiment_predictions", "id"), ("preprocessed", "id")):
                if table not in tables:
                    continue
                if postgres:
                    columns = {row[0] for row in execute(conn, f"SELECT * FROM {table} LIMIT 0").description}
                else:
                    columns = {row[1] for row in execute(conn, f"PRAGMA table_info({table})")}
                typed = (f"AND expired.content_type = {table}.content_type" if "content_type" in columns
                         else "AND NOT (EXISTS (SELECT 1 FROM posts WHERE posts.id = expired.id) AND "
                              "EXISTS (SELECT 1 FROM comments WHERE comments.id = expired.id))")
                counts[table] = execute(conn, f"""
                    DELETE FROM {table} WHERE EXISTS (
                        SELECT 1 FROM expired_reddit_records AS expired
                        WHERE expired.id = {table}.{key} {typed}
                    )
                """).rowcount
        for table, kind in ((comments, "comment"), (posts, "post")):
            if table in tables:
                counts[table] = execute(conn, f"""
                    DELETE FROM {table} WHERE id IN (
                        SELECT id FROM expired_reddit_records WHERE content_type = {marker}
                    )
                """, (kind,)).rowcount
        execute(conn, "DELETE FROM expired_reddit_records")
    execute(conn, "DROP TABLE expired_reddit_records")

    for table, column in (("sentiment_daily", "date"), ("sentiment_moving_avg", "date"),
                          ("change_points", "date"), ("topic_sentiment_trends", "date"),
                          ("topic_over_time", "week_start")):
        if table in tables:
            counts[table] = execute(conn, f"DELETE FROM {table} WHERE {column} < {marker}",
                                    (cutoff.date().isoformat(),)).rowcount
    return counts
