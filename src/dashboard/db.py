"""Dashboard data access layer — read-only SQLite queries with Streamlit caching."""

import os
import sqlite3
from datetime import date, timedelta
from typing import List, Optional, Tuple

import pandas as pd
import streamlit as st

DB_PATH = os.environ.get("REDDIT_DB_PATH", "historical_reddit_data.db")


def _connect() -> sqlite3.Connection:
    """Open a read-only connection to the SQLite database."""
    try:
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    except sqlite3.OperationalError:
        # DB file doesn't exist yet; open in-memory so callers get empty results
        conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


@st.cache_data(ttl=300)
def get_collection_summary() -> pd.DataFrame:
    """Return total post/comment counts and last collection timestamp."""
    try:
        conn = _connect()
        posts_row = conn.execute(
            "SELECT COUNT(*) AS n, MAX(timestamp) AS last_ts FROM posts"
        ).fetchone()
        comments_row = conn.execute("SELECT COUNT(*) AS n FROM comments").fetchone()
        conn.close()
        return pd.DataFrame(
            [
                {
                    "total_posts": posts_row["n"] or 0,
                    "total_comments": comments_row["n"] or 0,
                    "last_timestamp": posts_row["last_ts"],
                }
            ]
        )
    except Exception:
        return pd.DataFrame(
            columns=["total_posts", "total_comments", "last_timestamp"]
        )


@st.cache_data(ttl=300)
def get_last_ml_timestamp() -> Optional[str]:
    """Return the most recent predicted_at from sentiment_predictions."""
    try:
        conn = _connect()
        row = conn.execute(
            "SELECT MAX(predicted_at) AS ts FROM sentiment_predictions"
        ).fetchone()
        conn.close()
        return row["ts"] if row else None
    except Exception:
        return None


@st.cache_data(ttl=300)
def get_sentiment_summary() -> pd.DataFrame:
    """Return label counts and mean confidence from sentiment_predictions."""
    try:
        conn = _connect()
        df = pd.read_sql_query(
            """
            SELECT label, COUNT(*) AS count, AVG(confidence) AS mean_confidence
            FROM sentiment_predictions
            GROUP BY label
            """,
            conn,
        )
        conn.close()
        return df
    except Exception:
        return pd.DataFrame(columns=["label", "count", "mean_confidence"])


@st.cache_data(ttl=300)
def get_trending_topics(n: int = 3) -> pd.DataFrame:
    """Return top N topics by doc_count in the most recent week."""
    try:
        conn = _connect()
        df = pd.read_sql_query(
            """
            SELECT t.topic_id, t.keywords, tot.doc_count, tot.week_start
            FROM topic_over_time tot
            JOIN topics t ON tot.topic_id = t.topic_id
            WHERE tot.week_start = (SELECT MAX(week_start) FROM topic_over_time)
              AND t.topic_id != -1
            ORDER BY tot.doc_count DESC
            LIMIT ?
            """,
            conn,
            params=[n],
        )
        conn.close()
        return df
    except Exception:
        return pd.DataFrame(columns=["topic_id", "keywords", "doc_count", "week_start"])


@st.cache_data(ttl=300)
def get_daily_volume(subreddits: tuple = (), days: int = 30) -> pd.DataFrame:
    """Return daily post+comment counts per subreddit over the last N days."""
    try:
        conn = _connect()
        if subreddits:
            placeholders = ",".join("?" * len(subreddits))
            sql = f"""
                SELECT DATE(timestamp) AS date, subreddit, COUNT(*) AS count
                FROM (
                    SELECT timestamp, subreddit FROM posts
                    UNION ALL
                    SELECT timestamp, subreddit FROM comments
                )
                WHERE DATE(timestamp) >= DATE('now', ?)
                  AND subreddit IN ({placeholders})
                GROUP BY date, subreddit
                ORDER BY date
            """
            params: list = [f"-{days} days"] + list(subreddits)
        else:
            sql = """
                SELECT DATE(timestamp) AS date, subreddit, COUNT(*) AS count
                FROM (
                    SELECT timestamp, subreddit FROM posts
                    UNION ALL
                    SELECT timestamp, subreddit FROM comments
                )
                WHERE DATE(timestamp) >= DATE('now', ?)
                GROUP BY date, subreddit
                ORDER BY date
            """
            params = [f"-{days} days"]
        df = pd.read_sql_query(sql, conn, params=params)
        conn.close()
        return df
    except Exception:
        return pd.DataFrame(columns=["date", "subreddit", "count"])


@st.cache_data(ttl=300)
def get_sentiment_daily(subreddits: tuple = (), days: int = 90) -> pd.DataFrame:
    """Return daily sentiment with moving averages for the given subreddits."""
    try:
        conn = _connect()
        if subreddits:
            placeholders = ",".join("?" * len(subreddits))
            sql = f"""
                SELECT sd.subreddit, sd.date, sd.mean_score,
                       sma.rolling_7d, sma.rolling_30d
                FROM sentiment_daily sd
                LEFT JOIN sentiment_moving_avg sma
                    ON sd.subreddit = sma.subreddit AND sd.date = sma.date
                WHERE sd.date >= DATE('now', ?)
                  AND sd.subreddit IN ({placeholders})
                ORDER BY sd.date
            """
            params: list = [f"-{days} days"] + list(subreddits)
        else:
            sql = """
                SELECT sd.subreddit, sd.date, sd.mean_score,
                       sma.rolling_7d, sma.rolling_30d
                FROM sentiment_daily sd
                LEFT JOIN sentiment_moving_avg sma
                    ON sd.subreddit = sma.subreddit AND sd.date = sma.date
                WHERE sd.date >= DATE('now', ?)
                ORDER BY sd.date
            """
            params = [f"-{days} days"]
        df = pd.read_sql_query(sql, conn, params=params)
        conn.close()
        return df
    except Exception:
        return pd.DataFrame(
            columns=["subreddit", "date", "mean_score", "rolling_7d", "rolling_30d"]
        )


@st.cache_data(ttl=300)
def get_change_points(subreddits: tuple = ()) -> pd.DataFrame:
    """Return change points with magnitude for the given subreddits."""
    try:
        conn = _connect()
        if subreddits:
            placeholders = ",".join("?" * len(subreddits))
            sql = f"""
                SELECT subreddit, date, magnitude
                FROM change_points
                WHERE subreddit IN ({placeholders})
                ORDER BY date
            """
            df = pd.read_sql_query(sql, conn, params=list(subreddits))
        else:
            df = pd.read_sql_query(
                "SELECT subreddit, date, magnitude FROM change_points ORDER BY date",
                conn,
            )
        conn.close()
        return df
    except Exception:
        return pd.DataFrame(columns=["subreddit", "date", "magnitude"])


@st.cache_data(ttl=300)
def get_forecast(subreddits: tuple = ()) -> pd.DataFrame:
    """Return Prophet forecast with confidence bands."""
    try:
        conn = _connect()
        if subreddits:
            placeholders = ",".join("?" * len(subreddits))
            sql = f"""
                SELECT subreddit, date, yhat, yhat_lower, yhat_upper
                FROM sentiment_forecast
                WHERE subreddit IN ({placeholders})
                ORDER BY date
            """
            df = pd.read_sql_query(sql, conn, params=list(subreddits))
        else:
            df = pd.read_sql_query(
                """
                SELECT subreddit, date, yhat, yhat_lower, yhat_upper
                FROM sentiment_forecast
                ORDER BY date
                """,
                conn,
            )
        conn.close()
        return df
    except Exception:
        return pd.DataFrame(
            columns=["subreddit", "date", "yhat", "yhat_lower", "yhat_upper"]
        )


@st.cache_data(ttl=300)
def get_topics() -> pd.DataFrame:
    """Return all non-outlier topics with keywords and stats."""
    try:
        conn = _connect()
        df = pd.read_sql_query(
            """
            SELECT topic_id, keywords, doc_count, coherence_score
            FROM topics
            WHERE topic_id != -1
            ORDER BY doc_count DESC
            """,
            conn,
        )
        conn.close()
        return df
    except Exception:
        return pd.DataFrame(
            columns=["topic_id", "keywords", "doc_count", "coherence_score"]
        )


@st.cache_data(ttl=300)
def get_emerging_topics(days: int = 7) -> pd.DataFrame:
    """Return topics created within the last N days."""
    try:
        conn = _connect()
        df = pd.read_sql_query(
            """
            SELECT topic_id, keywords, doc_count
            FROM topics
            WHERE topic_id != -1
              AND created_at >= datetime('now', ?)
            ORDER BY doc_count DESC
            """,
            conn,
            params=[f"-{days} days"],
        )
        conn.close()
        return df
    except Exception:
        return pd.DataFrame(columns=["topic_id", "keywords", "doc_count"])


@st.cache_data(ttl=300)
def get_topic_over_time(topic_id: int) -> pd.DataFrame:
    """Return weekly doc count and avg sentiment for a single topic."""
    try:
        conn = _connect()
        df = pd.read_sql_query(
            """
            SELECT week_start, doc_count, avg_sentiment
            FROM topic_over_time
            WHERE topic_id = ?
            ORDER BY week_start
            """,
            conn,
            params=[topic_id],
        )
        conn.close()
        return df
    except Exception:
        return pd.DataFrame(columns=["week_start", "doc_count", "avg_sentiment"])


@st.cache_data(ttl=300)
def get_topic_heatmap(n: int = 30) -> pd.DataFrame:
    """Return pivot DataFrame: topic_id (rows) × week_start (cols) = avg_sentiment."""
    try:
        conn = _connect()
        df = pd.read_sql_query(
            """
            SELECT topic_id, week_start, avg_sentiment
            FROM topic_over_time
            WHERE topic_id IN (
                SELECT topic_id FROM topics
                WHERE topic_id != -1
                ORDER BY doc_count DESC
                LIMIT ?
            )
            ORDER BY week_start
            """,
            conn,
            params=[n],
        )
        conn.close()
        if df.empty:
            return df
        return df.pivot(index="topic_id", columns="week_start", values="avg_sentiment")
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=300)
def get_deep_dive(
    keyword: str = "",
    subreddits: tuple = (),
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    label_filter: str = "all",
    content_type_filter: str = "both",
) -> pd.DataFrame:
    """Return filtered records joining preprocessed, sentiment, and source tables."""
    try:
        conn = _connect()
        conditions: list = []
        params: list = []

        if keyword:
            conditions.append("p.clean_text LIKE ?")
            params.append(f"%{keyword}%")

        if subreddits:
            placeholders = ",".join("?" * len(subreddits))
            conditions.append(f"src.subreddit IN ({placeholders})")
            params.extend(list(subreddits))

        if start_date:
            conditions.append("DATE(src.timestamp) >= ?")
            params.append(start_date)

        if end_date:
            conditions.append("DATE(src.timestamp) <= ?")
            params.append(end_date)

        if label_filter != "all":
            conditions.append("sp.label = ?")
            params.append(label_filter)

        if content_type_filter != "both":
            conditions.append("p.content_type = ?")
            params.append(content_type_filter)

        where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""

        sql = f"""
            SELECT
                DATE(src.timestamp) AS date,
                src.subreddit,
                p.content_type,
                p.clean_text,
                sp.label,
                sp.confidence
            FROM preprocessed p
            JOIN sentiment_predictions sp ON p.id = sp.id
            JOIN (
                SELECT id, timestamp, subreddit, 'post' AS content_type FROM posts
                UNION ALL
                SELECT id, timestamp, subreddit, 'comment' AS content_type FROM comments
            ) src ON p.id = src.id AND p.content_type = src.content_type
            {where_clause}
            ORDER BY src.timestamp DESC
        """
        df = pd.read_sql_query(sql, conn, params=params)
        conn.close()
        return df
    except Exception:
        return pd.DataFrame(
            columns=["date", "subreddit", "content_type", "clean_text", "label", "confidence"]
        )


@st.cache_data(ttl=300)
def get_vader_agreement() -> pd.DataFrame:
    """Return per-subreddit VADER vs model agreement rates (capped at 10k rows)."""
    try:
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

        conn = _connect()
        df = pd.read_sql_query(
            """
            SELECT p.clean_text, sp.label,
                   COALESCE(posts.subreddit, comments.subreddit) AS subreddit
            FROM preprocessed p
            JOIN sentiment_predictions sp ON p.id = sp.id
            LEFT JOIN posts ON p.id = posts.id AND p.content_type = 'post'
            LEFT JOIN comments ON p.id = comments.id AND p.content_type = 'comment'
            WHERE p.is_filtered = 0
              AND p.clean_text IS NOT NULL
            LIMIT 10000
            """,
            conn,
        )
        conn.close()

        if df.empty:
            return pd.DataFrame(columns=["subreddit", "agreement_rate", "total"])

        analyzer = SentimentIntensityAnalyzer()

        def _vader_sign(text: str) -> int:
            compound = analyzer.polarity_scores(str(text))["compound"]
            if compound > 0.05:
                return 1
            if compound < -0.05:
                return -1
            return 0

        _label_sign = {"positive": 1, "neutral": 0, "negative": -1}
        df["vader_sign"] = df["clean_text"].apply(_vader_sign)
        df["model_sign"] = df["label"].map(_label_sign).fillna(0).astype(int)
        df["agree"] = df["vader_sign"] == df["model_sign"]

        return (
            df.groupby("subreddit")
            .agg(agreement_rate=("agree", "mean"), total=("agree", "count"))
            .reset_index()
        )
    except Exception:
        return pd.DataFrame(columns=["subreddit", "agreement_rate", "total"])


@st.cache_data(ttl=300)
def get_known_subreddits() -> List[str]:
    """Return sorted list of distinct subreddit names from posts."""
    try:
        conn = _connect()
        rows = conn.execute(
            "SELECT DISTINCT subreddit FROM posts ORDER BY subreddit"
        ).fetchall()
        conn.close()
        return [r[0] for r in rows if r[0]]
    except Exception:
        return []


@st.cache_data(ttl=300)
def get_date_range() -> Tuple[date, date]:
    """Return (min_date, max_date) from posts.timestamp as Python date objects."""
    try:
        conn = _connect()
        row = conn.execute(
            "SELECT MIN(DATE(timestamp)), MAX(DATE(timestamp)) FROM posts"
        ).fetchone()
        conn.close()
        if row and row[0] and row[1]:
            return date.fromisoformat(row[0]), date.fromisoformat(row[1])
    except Exception:
        pass
    today = date.today()
    return today - timedelta(days=30), today
