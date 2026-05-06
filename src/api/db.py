"""Read-only dashboard queries for the FastAPI layer — no Streamlit dependency."""

import json
import logging
import re
import time
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from functools import wraps
from typing import List, Optional, Tuple

import pandas as pd

from src.db.connection import (
    false_literal,
    execute,
    get_backend,
    get_read_connection,
    is_postgres_connection,
    paramstyle,
    placeholders,
    recent_interval_params,
    recent_interval_sql,
    release_connection,
)

logger = logging.getLogger(__name__)
ACTIVE_BACKEND = get_backend()
KEYWORD_SPLIT_RE = re.compile(r"[\s,;|/]+")
TOPIC_GRAPH_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "in",
    "is",
    "it",
    "my",
    "of",
    "on",
    "or",
    "that",
    "the",
    "this",
    "to",
    "with",
}


def _ttl_cache(seconds: int = 30, maxsize: int = 128):
    def decorator(fn):
        cache: dict[tuple, tuple[float, object]] = {}

        @wraps(fn)
        def wrapper(*args, **kwargs):
            now = time.monotonic()
            key = (args, tuple(sorted(kwargs.items())))
            cached = cache.get(key)
            if cached and now - cached[0] < seconds:
                return deepcopy(cached[1])
            value = fn(*args, **kwargs)
            if len(cache) >= maxsize:
                oldest = min(cache, key=lambda item: cache[item][0])
                cache.pop(oldest, None)
            cache[key] = (now, deepcopy(value))
            return value

        return wrapper

    return decorator


def _connect():
    return get_read_connection()


def _close(conn) -> None:
    release_connection(conn)


def get_table_state(required_tables: Tuple[str, ...]) -> dict:
    try:
        conn = _connect()
        marker = paramstyle()
        missing = []
        for table in required_tables:
            if is_postgres_connection(conn):
                row = execute(
                    conn,
                    f"""
                    SELECT 1
                    FROM information_schema.tables
                    WHERE table_schema = 'public' AND table_name = {marker}
                    LIMIT 1
                    """,
                    (table,),
                ).fetchone()
            else:
                row = execute(
                    conn,
                    f"SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = {marker}",
                    (table,),
                ).fetchone()
            if row is None:
                missing.append(table)
        _close(conn)
        return {
            "state": "missing_schema" if missing else "ready",
            "missing_tables": missing,
            "reason": f"Missing tables: {', '.join(missing)}" if missing else None,
        }
    except Exception as exc:
        logger.exception("Failed to inspect dashboard table state")
        return {"state": "error", "missing_tables": [], "reason": str(exc)}


def _exclusive_end_date(end_date: Optional[str]) -> Optional[str]:
    if not end_date:
        return None
    return (datetime.strptime(end_date, "%Y-%m-%d").date() + timedelta(days=1)).isoformat()


def _source_conditions(
    table_alias: str,
    subreddits: Tuple[str, ...] = (),
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    timestamp_column: str = "timestamp",
) -> tuple[str, list]:
    conditions: list[str] = []
    params: list = []
    marker = paramstyle()

    if subreddits:
        conditions.append(f"{table_alias}.subreddit IN ({placeholders(len(subreddits))})")
        params.extend(list(subreddits))
    if start_date:
        conditions.append(f"{table_alias}.{timestamp_column} >= {marker}")
        params.append(start_date)
    if end_date:
        conditions.append(f"{table_alias}.{timestamp_column} < {marker}")
        params.append(_exclusive_end_date(end_date))

    return (("WHERE " + " AND ".join(conditions)) if conditions else "", params)


def _sentiment_source_conditions(
    subreddits: Tuple[str, ...] = (),
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> tuple[str, list]:
    conditions: list[str] = []
    params: list = []
    marker = paramstyle()

    if subreddits:
        conditions.append(f"src.subreddit IN ({placeholders(len(subreddits))})")
        params.extend(list(subreddits))
    if start_date:
        conditions.append(f"src.timestamp >= {marker}")
        params.append(start_date)
    if end_date:
        conditions.append(f"src.timestamp < {marker}")
        params.append(_exclusive_end_date(end_date))

    return (("WHERE " + " AND ".join(conditions)) if conditions else "", params)


@_ttl_cache(seconds=30)
def get_collection_summary(
    subreddits: Tuple[str, ...] = (),
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> dict:
    try:
        conn = _connect()
        posts_where, posts_params = _source_conditions("posts", subreddits, start_date, end_date)
        comments_where, comments_params = _source_conditions("comments", subreddits, start_date, end_date)
        sentiment_where, sentiment_params = _sentiment_source_conditions(subreddits, start_date, end_date)
        posts_row = execute(
            conn,
            f"SELECT COUNT(*) AS n, MAX(timestamp) AS last_ts FROM posts {posts_where}",
            posts_params,
        ).fetchone()
        comments_row = execute(
            conn,
            f"SELECT COUNT(*) AS n FROM comments {comments_where}",
            comments_params,
        ).fetchone()
        if subreddits:
            ml_row = execute(
                conn,
                f"""
                SELECT MAX(sp.predicted_at) AS ts
                FROM sentiment_predictions sp
                JOIN preprocessed p ON sp.id = p.id
                JOIN (
                    SELECT id, timestamp, subreddit, 'post' AS content_type FROM posts
                    UNION ALL
                    SELECT id, timestamp, subreddit, 'comment' AS content_type FROM comments
                ) src ON p.id = src.id AND p.content_type = src.content_type
                {sentiment_where}
                """,
                sentiment_params,
            ).fetchone()
        else:
            ml_row = execute(
                conn,
                "SELECT MAX(predicted_at) AS ts FROM sentiment_predictions",
            ).fetchone()
        _close(conn)
        return {
            "total_posts": posts_row["n"] or 0,
            "total_comments": comments_row["n"] or 0,
            "last_timestamp": posts_row["last_ts"],
            "last_ml_timestamp": ml_row["ts"] if ml_row else None,
        }
    except Exception:
        logger.exception("Failed to read collection summary")
        return {"total_posts": 0, "total_comments": 0, "last_timestamp": None, "last_ml_timestamp": None}


@_ttl_cache(seconds=30)
def get_trending_topics(n: int = 3) -> List[dict]:
    try:
        conn = _connect()
        df = pd.read_sql_query(
            f"""
            SELECT t.topic_id, t.keywords, tot.doc_count, tot.week_start
            FROM topic_over_time tot
            JOIN topics t ON tot.topic_id = t.topic_id
            WHERE tot.week_start = (SELECT MAX(week_start) FROM topic_over_time)
              AND t.topic_id != -1
            ORDER BY tot.doc_count DESC
            LIMIT {paramstyle()}
            """,
            conn,
            params=[n],
        )
        _close(conn)
        return df.to_dict(orient="records")
    except Exception:
        logger.exception("Failed to read trending topics")
        return []


@_ttl_cache(seconds=30)
def get_sentiment_summary(
    subreddits: Tuple[str, ...] = (),
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    weighted: bool = False,
) -> List[dict]:
    try:
        conn = _connect()
        marker = paramstyle()
        post_conditions = ["p.content_type = 'post'"]
        comment_conditions = ["p.content_type = 'comment'"]
        post_params: list = []
        comment_params: list = []

        if subreddits:
            subreddit_clause = placeholders(len(subreddits))
            post_conditions.append(f"posts.subreddit IN ({subreddit_clause})")
            comment_conditions.append(f"comments.subreddit IN ({subreddit_clause})")
            post_params.extend(list(subreddits))
            comment_params.extend(list(subreddits))
        if start_date:
            post_conditions.append(f"posts.timestamp >= {marker}")
            comment_conditions.append(f"comments.timestamp >= {marker}")
            post_params.append(start_date)
            comment_params.append(start_date)
        if end_date:
            exclusive_end = _exclusive_end_date(end_date)
            post_conditions.append(f"posts.timestamp < {marker}")
            comment_conditions.append(f"comments.timestamp < {marker}")
            post_params.append(exclusive_end)
            comment_params.append(exclusive_end)

        post_weight = "(1 + COALESCE(posts.upvotes, 0) + COALESCE(posts.num_comments, 0))"
        comment_weight = "(1 + COALESCE(comments.upvotes, 0))"
        post_count_expr = f"SUM({post_weight})" if weighted else "COUNT(*)"
        comment_count_expr = f"SUM({comment_weight})" if weighted else "COUNT(*)"
        post_conf_expr = f"SUM(sp.confidence * {post_weight})" if weighted else "SUM(sp.confidence)"
        comment_conf_expr = f"SUM(sp.confidence * {comment_weight})" if weighted else "SUM(sp.confidence)"

        df = pd.read_sql_query(
            f"""
            SELECT label,
                   SUM(raw_count) AS count,
                   SUM(weighted_count) AS weighted_count,
                   SUM(confidence_sum) / NULLIF(SUM(weighted_count), 0) AS mean_confidence
            FROM (
                SELECT sp.label,
                       COUNT(*) AS raw_count,
                       {post_count_expr} AS weighted_count,
                       {post_conf_expr} AS confidence_sum
                FROM posts
                JOIN preprocessed p ON posts.id = p.id
                JOIN sentiment_predictions sp ON p.id = sp.id
                WHERE {" AND ".join(post_conditions)}
                GROUP BY sp.label
                UNION ALL
                SELECT sp.label,
                       COUNT(*) AS raw_count,
                       {comment_count_expr} AS weighted_count,
                       {comment_conf_expr} AS confidence_sum
                FROM comments
                JOIN preprocessed p ON comments.id = p.id
                JOIN sentiment_predictions sp ON p.id = sp.id
                WHERE {" AND ".join(comment_conditions)}
                GROUP BY sp.label
            )
            GROUP BY label
            """,
            conn,
            params=post_params + comment_params,
        )
        _close(conn)
        rows = df.to_dict(orient="records")
        for row in rows:
            row["weighted"] = weighted
        return rows
    except Exception:
        logger.exception("Failed to read sentiment summary")
        return []


@_ttl_cache(seconds=30)
def get_daily_volume(
    subreddits: Tuple[str, ...] = (),
    days: int = 30,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> List[dict]:
    try:
        conn = _connect()
        conditions: list[str] = []
        params: list = []
        marker = paramstyle()

        if start_date:
            conditions.append(f"timestamp >= {marker}")
            params.append(start_date)
        if end_date:
            conditions.append(f"timestamp < {marker}")
            params.append(_exclusive_end_date(end_date))
        if not start_date and not end_date:
            conditions.append(recent_interval_sql("DATE(timestamp)", days, date_only=True))
            params.extend(recent_interval_params(days))
        if subreddits:
            conditions.append(f"subreddit IN ({placeholders(len(subreddits))})")
            params.extend(list(subreddits))
        where_clause = "WHERE " + " AND ".join(conditions)
        sql = f"""
            SELECT DATE(timestamp) AS date, subreddit, COUNT(*) AS count
            FROM (
                SELECT timestamp, subreddit FROM posts
                UNION ALL
                SELECT timestamp, subreddit FROM comments
            )
            {where_clause}
            GROUP BY date, subreddit
            ORDER BY date
        """
        df = pd.read_sql_query(sql, conn, params=params)
        _close(conn)
        return df.to_dict(orient="records")
    except Exception:
        logger.exception("Failed to read daily volume")
        return []


@_ttl_cache(seconds=30)
def get_sentiment_daily(
    subreddits: Tuple[str, ...] = (),
    days: int = 90,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> List[dict]:
    try:
        conn = _connect()
        conditions: list[str] = []
        params: list = []
        marker = paramstyle()

        if start_date:
            conditions.append(f"sd.date >= {marker}")
            params.append(start_date)
        if end_date:
            conditions.append(f"sd.date <= {marker}")
            params.append(end_date)
        if not start_date and not end_date:
            conditions.append(recent_interval_sql("sd.date", days, date_only=True))
            params.extend(recent_interval_params(days))
        if subreddits:
            conditions.append(f"sd.subreddit IN ({placeholders(len(subreddits))})")
            params.extend(list(subreddits))
        sql = f"""
            SELECT sd.subreddit, sd.date, sd.mean_score,
                   sma.rolling_7d, sma.rolling_30d
            FROM sentiment_daily sd
            LEFT JOIN sentiment_moving_avg sma
                ON sd.subreddit = sma.subreddit AND sd.date = sma.date
            WHERE {" AND ".join(conditions)}
            ORDER BY sd.date
        """
        df = pd.read_sql_query(sql, conn, params=params)
        _close(conn)
        return df.to_dict(orient="records")
    except Exception:
        logger.exception("Failed to read daily sentiment")
        return []


def get_change_points(subreddits: Tuple[str, ...] = ()) -> List[dict]:
    try:
        conn = _connect()
        if subreddits:
            subreddit_placeholders = placeholders(len(subreddits))
            sql = f"SELECT subreddit, date, magnitude FROM change_points WHERE subreddit IN ({subreddit_placeholders}) ORDER BY date"
            df = pd.read_sql_query(sql, conn, params=list(subreddits))
        else:
            df = pd.read_sql_query(
                "SELECT subreddit, date, magnitude FROM change_points ORDER BY date", conn
            )
        _close(conn)
        return df.to_dict(orient="records")
    except Exception:
        logger.exception("Failed to read change points")
        return []


def get_forecast(subreddits: Tuple[str, ...] = ()) -> List[dict]:
    try:
        conn = _connect()
        if subreddits:
            subreddit_placeholders = placeholders(len(subreddits))
            sql = f"SELECT subreddit, date, yhat, yhat_lower, yhat_upper FROM sentiment_forecast WHERE subreddit IN ({subreddit_placeholders}) ORDER BY date"
            df = pd.read_sql_query(sql, conn, params=list(subreddits))
        else:
            df = pd.read_sql_query(
                "SELECT subreddit, date, yhat, yhat_lower, yhat_upper FROM sentiment_forecast ORDER BY date",
                conn,
            )
        _close(conn)
        return df.to_dict(orient="records")
    except Exception:
        logger.exception("Failed to read forecast")
        return []


def get_topics() -> List[dict]:
    try:
        conn = _connect()
        df = pd.read_sql_query(
            "SELECT topic_id, keywords, doc_count, coherence_score FROM topics WHERE topic_id != -1 ORDER BY doc_count DESC",
            conn,
        )
        _close(conn)
        return df.to_dict(orient="records")
    except Exception:
        logger.exception("Failed to read topics")
        return []


def _topic_keywords(value: object) -> list[str]:
    if value is None:
        return []
    text = str(value).strip()
    if not text:
        return []
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        parsed = None

    if isinstance(parsed, list):
        candidates = [str(item) for item in parsed]
    else:
        candidates = KEYWORD_SPLIT_RE.split(text.replace("[", " ").replace("]", " ").replace('"', " "))

    seen: set[str] = set()
    keywords: list[str] = []
    for candidate in candidates:
        keyword = candidate.strip().lower()
        if keyword and keyword not in TOPIC_GRAPH_STOPWORDS and keyword not in seen:
            seen.add(keyword)
            keywords.append(keyword)
    return keywords


def get_topic_graph(
    n: int = 50,
    min_similarity: float = 0.15,
    subreddits: Tuple[str, ...] = (),
) -> dict:
    try:
        limit = max(1, min(int(n), 100))
        threshold = max(0.0, min(float(min_similarity), 1.0))
        conn = _connect()
        if subreddits:
            df = pd.read_sql_query(
                f"""
                SELECT
                    t.topic_id,
                    t.keywords,
                    COUNT(ta.id) AS doc_count,
                    t.coherence_score,
                    t.created_at
                FROM topic_assignments ta
                JOIN topics t ON ta.topic_id = t.topic_id
                JOIN (
                    SELECT id, subreddit FROM posts
                    UNION ALL
                    SELECT id, subreddit FROM comments
                ) src ON src.id = ta.id
                WHERE t.topic_id != -1
                  AND src.subreddit IN ({placeholders(len(subreddits))})
                GROUP BY t.topic_id, t.keywords, t.coherence_score, t.created_at
                ORDER BY doc_count DESC, t.topic_id ASC
                LIMIT {paramstyle()}
                """,
                conn,
                params=[*subreddits, limit],
            )
        else:
            df = pd.read_sql_query(
                f"""
                SELECT topic_id, keywords, doc_count, coherence_score, created_at
                FROM topics
                WHERE topic_id != -1
                ORDER BY doc_count DESC, topic_id ASC
                LIMIT {paramstyle()}
                """,
                conn,
                params=[limit],
            )
        _close(conn)

        rows = df.to_dict(orient="records")
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        nodes: list[dict] = []
        keyword_sets: dict[int, set[str]] = {}

        for row in rows:
            topic_id = int(row["topic_id"])
            keywords = _topic_keywords(row.get("keywords"))
            keyword_sets[topic_id] = set(keywords)
            created_at = row.get("created_at")
            emerging = False
            if created_at:
                try:
                    created = datetime.fromisoformat(str(created_at).replace("Z", "+00:00")).replace(tzinfo=None)
                    emerging = (now - created).days <= 7
                except ValueError:
                    emerging = False
            nodes.append(
                {
                    "topic_id": topic_id,
                    "keywords": row.get("keywords") or "",
                    "keyword_terms": keywords,
                    "doc_count": int(row.get("doc_count") or 0),
                    "coherence_score": row.get("coherence_score"),
                    "emerging": emerging,
                }
            )

        edges: list[dict] = []
        for source_index, source in enumerate(nodes):
            source_terms = keyword_sets[source["topic_id"]]
            if not source_terms:
                continue
            for target in nodes[source_index + 1:]:
                target_terms = keyword_sets[target["topic_id"]]
                if not target_terms:
                    continue
                shared = sorted(source_terms & target_terms)
                if not shared:
                    continue
                similarity = len(shared) / len(source_terms | target_terms)
                if similarity >= threshold:
                    edges.append(
                        {
                            "source": source["topic_id"],
                            "target": target["topic_id"],
                            "similarity": round(similarity, 4),
                            "shared_keywords": shared,
                        }
                    )

        edges.sort(key=lambda edge: (-edge["similarity"], edge["source"], edge["target"]))
        return {"nodes": nodes, "edges": edges}
    except Exception:
        logger.exception("Failed to build topic graph")
        return {"nodes": [], "edges": []}


def get_emerging_topics(days: int = 7) -> List[dict]:
    try:
        conn = _connect()
        df = pd.read_sql_query(
            f"SELECT topic_id, keywords, doc_count FROM topics WHERE topic_id != -1 AND {recent_interval_sql('created_at', days)} ORDER BY doc_count DESC",
            conn,
            params=recent_interval_params(days),
        )
        _close(conn)
        return df.to_dict(orient="records")
    except Exception:
        logger.exception("Failed to read emerging topics")
        return []


def get_topic_over_time(topic_id: int) -> List[dict]:
    try:
        conn = _connect()
        df = pd.read_sql_query(
            f"SELECT week_start, doc_count, avg_sentiment FROM topic_over_time WHERE topic_id = {paramstyle()} ORDER BY week_start",
            conn,
            params=[topic_id],
        )
        _close(conn)
        return df.to_dict(orient="records")
    except Exception:
        logger.exception("Failed to read topic over time")
        return []


def get_topic_heatmap(n: int = 30) -> List[dict]:
    try:
        conn = _connect()
        df = pd.read_sql_query(
            f"""
            SELECT topic_id, week_start, avg_sentiment
            FROM topic_over_time
            WHERE topic_id IN (
                SELECT topic_id FROM topics WHERE topic_id != -1
                ORDER BY doc_count DESC LIMIT {paramstyle()}
            )
            ORDER BY topic_id, week_start
            """,
            conn,
            params=[n],
        )
        _close(conn)
        return df.to_dict(orient="records")
    except Exception:
        logger.exception("Failed to read topic heatmap")
        return []


def get_deep_dive(
    keyword: str = "",
    subreddits: Tuple[str, ...] = (),
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    label_filter: str = "all",
    content_type_filter: str = "both",
    limit: int = 500,
    offset: int = 0,
) -> List[dict]:
    try:
        conn = _connect()
        conditions: list = []
        params: list = []
        marker = paramstyle()

        if keyword:
            conditions.append(f"p.clean_text LIKE {marker}")
            params.append(f"%{keyword}%")
        if subreddits:
            subreddit_placeholders = placeholders(len(subreddits))
            conditions.append(f"src.subreddit IN ({subreddit_placeholders})")
            params.extend(list(subreddits))
        if start_date:
            conditions.append(f"DATE(src.timestamp) >= {marker}")
            params.append(start_date)
        if end_date:
            conditions.append(f"DATE(src.timestamp) <= {marker}")
            params.append(end_date)
        if label_filter != "all":
            conditions.append(f"sp.label = {marker}")
            params.append(label_filter)
        if content_type_filter != "both":
            conditions.append(f"p.content_type = {marker}")
            params.append(content_type_filter)

        where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        sql = f"""
            SELECT DATE(src.timestamp) AS date, src.subreddit,
                   p.content_type, p.clean_text, sp.label, sp.confidence
            FROM preprocessed p
            JOIN sentiment_predictions sp ON p.id = sp.id
            JOIN (
                SELECT id, timestamp, subreddit, 'post' AS content_type FROM posts
                UNION ALL
                SELECT id, timestamp, subreddit, 'comment' AS content_type FROM comments
            ) src ON p.id = src.id AND p.content_type = src.content_type
            {where_clause}
            ORDER BY src.timestamp DESC
            LIMIT {marker} OFFSET {marker}
        """
        params += [limit, offset]
        df = pd.read_sql_query(sql, conn, params=params)
        _close(conn)
        return df.to_dict(orient="records")
    except Exception:
        logger.exception("Failed to read deep dive")
        return []


def get_vader_agreement() -> List[dict]:
    try:
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

        conn = _connect()
        df = pd.read_sql_query(
            f"""
            SELECT p.clean_text, sp.label,
                   COALESCE(posts.subreddit, comments.subreddit) AS subreddit
            FROM preprocessed p
            JOIN sentiment_predictions sp ON p.id = sp.id
            LEFT JOIN posts ON p.id = posts.id AND p.content_type = 'post'
            LEFT JOIN comments ON p.id = comments.id AND p.content_type = 'comment'
            WHERE p.is_filtered = {false_literal()} AND p.clean_text IS NOT NULL
            LIMIT 10000
            """,
            conn,
        )
        _close(conn)
        if df.empty:
            return []

        analyzer = SentimentIntensityAnalyzer()

        def _vader_sign(text: str) -> int:
            c = analyzer.polarity_scores(str(text))["compound"]
            return 1 if c > 0.05 else (-1 if c < -0.05 else 0)

        _label_sign = {"positive": 1, "neutral": 0, "negative": -1}
        df["vader_sign"] = df["clean_text"].apply(_vader_sign)
        df["model_sign"] = df["label"].map(_label_sign).fillna(0).astype(int)
        df["agree"] = df["vader_sign"] == df["model_sign"]

        result = (
            df.groupby("subreddit")
            .agg(agreement_rate=("agree", "mean"), total=("agree", "count"))
            .reset_index()
        )
        return result.to_dict(orient="records")
    except Exception:
        logger.exception("Failed to compute VADER agreement")
        return []


def get_low_confidence_examples(limit: int = 50) -> List[dict]:
    try:
        conn = _connect()
        df = pd.read_sql_query(
            f"""
            SELECT p.id, DATE(src.timestamp) AS date, src.subreddit, p.content_type,
                   p.clean_text, sp.label, sp.confidence
            FROM preprocessed p
            JOIN sentiment_predictions sp ON p.id = sp.id
            JOIN (
                SELECT id, timestamp, subreddit, 'post' AS content_type FROM posts
                UNION ALL
                SELECT id, timestamp, subreddit, 'comment' AS content_type FROM comments
            ) src ON p.id = src.id AND p.content_type = src.content_type
            WHERE p.is_filtered = {false_literal()}
            ORDER BY sp.confidence ASC, src.timestamp DESC
            LIMIT {paramstyle()}
            """,
            conn,
            params=[limit],
        )
        _close(conn)
        rows = df.to_dict(orient="records")
        for row in rows:
            row["text_preview"] = str(row.pop("clean_text") or "")[:220]
        return rows
    except Exception:
        logger.exception("Failed to read low confidence examples")
        return []


def get_vader_disagreements(limit: int = 50) -> List[dict]:
    try:
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

        conn = _connect()
        df = pd.read_sql_query(
            f"""
            SELECT p.id, DATE(src.timestamp) AS date, src.subreddit, p.content_type,
                   p.clean_text, sp.label, sp.confidence
            FROM preprocessed p
            JOIN sentiment_predictions sp ON p.id = sp.id
            JOIN (
                SELECT id, timestamp, subreddit, 'post' AS content_type FROM posts
                UNION ALL
                SELECT id, timestamp, subreddit, 'comment' AS content_type FROM comments
            ) src ON p.id = src.id AND p.content_type = src.content_type
            WHERE p.is_filtered = {false_literal()} AND p.clean_text IS NOT NULL
            ORDER BY src.timestamp DESC
            LIMIT 5000
            """,
            conn,
        )
        _close(conn)
        if df.empty:
            return []
        analyzer = SentimentIntensityAnalyzer()
        label_sign = {"positive": 1, "neutral": 0, "negative": -1}

        def vader_label(text: str) -> str:
            compound = analyzer.polarity_scores(str(text))["compound"]
            if compound > 0.05:
                return "positive"
            if compound < -0.05:
                return "negative"
            return "neutral"

        df["vader_label"] = df["clean_text"].apply(vader_label)
        df["model_sign"] = df["label"].map(label_sign).fillna(0).astype(int)
        df["vader_sign"] = df["vader_label"].map(label_sign).fillna(0).astype(int)
        disagreements = df[df["model_sign"] != df["vader_sign"]].sort_values(["confidence"], ascending=[False]).head(limit)
        rows = disagreements.to_dict(orient="records")
        for row in rows:
            row["text_preview"] = str(row.pop("clean_text") or "")[:220]
            row.pop("model_sign", None)
            row.pop("vader_sign", None)
        return rows
    except Exception:
        logger.exception("Failed to compute VADER disagreements")
        return []


def get_confidence_by_subreddit() -> List[dict]:
    try:
        conn = _connect()
        df = pd.read_sql_query(
            """
            SELECT src.subreddit,
                   COUNT(*) AS total,
                   AVG(sp.confidence) AS mean_confidence,
                   SUM(CASE WHEN sp.confidence < 0.6 THEN 1 ELSE 0 END) AS low_confidence_count
            FROM preprocessed p
            JOIN sentiment_predictions sp ON p.id = sp.id
            JOIN (
                SELECT id, subreddit, 'post' AS content_type FROM posts
                UNION ALL
                SELECT id, subreddit, 'comment' AS content_type FROM comments
            ) src ON p.id = src.id AND p.content_type = src.content_type
            GROUP BY src.subreddit
            ORDER BY mean_confidence ASC, total DESC
            """,
            conn,
        )
        _close(conn)
        return df.to_dict(orient="records")
    except Exception:
        logger.exception("Failed to read confidence by subreddit")
        return []


@_ttl_cache(seconds=60)
def get_known_subreddits() -> List[str]:
    try:
        conn = _connect()
        rows = execute(
            conn,
            "SELECT DISTINCT subreddit FROM posts ORDER BY subreddit"
        ).fetchall()
        _close(conn)
        return [r[0] for r in rows if r[0]]
    except Exception:
        logger.exception("Failed to read known subreddits")
        return []


@_ttl_cache(seconds=60)
def get_date_range() -> dict:
    try:
        conn = _connect()
        row = execute(
            conn,
            "SELECT MIN(DATE(timestamp)), MAX(DATE(timestamp)) FROM posts"
        ).fetchone()
        _close(conn)
        if row and row[0] and row[1]:
            return {"start": row[0], "end": row[1]}
    except Exception:
        logger.exception("Failed to read date range")
    today = date.today()
    return {"start": str(today - timedelta(days=30)), "end": str(today)}
