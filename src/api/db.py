"""Read-only SQLite queries for the FastAPI layer — no Streamlit dependency."""

import os
import sqlite3
from datetime import date, timedelta
from typing import List, Optional, Tuple

import pandas as pd

DB_PATH = os.environ.get("REDDIT_DB_PATH", "historical_reddit_data.db")


def _connect() -> sqlite3.Connection:
    try:
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    except sqlite3.OperationalError:
        conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


def get_collection_summary() -> dict:
    try:
        conn = _connect()
        posts_row = conn.execute(
            "SELECT COUNT(*) AS n, MAX(timestamp) AS last_ts FROM posts"
        ).fetchone()
        comments_row = conn.execute("SELECT COUNT(*) AS n FROM comments").fetchone()
        ml_row = conn.execute(
            "SELECT MAX(predicted_at) AS ts FROM sentiment_predictions"
        ).fetchone()
        conn.close()
        return {
            "total_posts": posts_row["n"] or 0,
            "total_comments": comments_row["n"] or 0,
            "last_timestamp": posts_row["last_ts"],
            "last_ml_timestamp": ml_row["ts"] if ml_row else None,
        }
    except Exception:
        return {"total_posts": 0, "total_comments": 0, "last_timestamp": None, "last_ml_timestamp": None}


def get_trending_topics(n: int = 3) -> List[dict]:
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
        return df.to_dict(orient="records")
    except Exception:
        return []


def get_sentiment_summary() -> List[dict]:
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
        return df.to_dict(orient="records")
    except Exception:
        return []


def get_daily_volume(subreddits: Tuple[str, ...] = (), days: int = 30) -> List[dict]:
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
        return df.to_dict(orient="records")
    except Exception:
        return []


def get_sentiment_daily(subreddits: Tuple[str, ...] = (), days: int = 90) -> List[dict]:
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
        return df.to_dict(orient="records")
    except Exception:
        return []


def get_change_points(subreddits: Tuple[str, ...] = ()) -> List[dict]:
    try:
        conn = _connect()
        if subreddits:
            placeholders = ",".join("?" * len(subreddits))
            sql = f"SELECT subreddit, date, magnitude FROM change_points WHERE subreddit IN ({placeholders}) ORDER BY date"
            df = pd.read_sql_query(sql, conn, params=list(subreddits))
        else:
            df = pd.read_sql_query(
                "SELECT subreddit, date, magnitude FROM change_points ORDER BY date", conn
            )
        conn.close()
        return df.to_dict(orient="records")
    except Exception:
        return []


def get_forecast(subreddits: Tuple[str, ...] = ()) -> List[dict]:
    try:
        conn = _connect()
        if subreddits:
            placeholders = ",".join("?" * len(subreddits))
            sql = f"SELECT subreddit, date, yhat, yhat_lower, yhat_upper FROM sentiment_forecast WHERE subreddit IN ({placeholders}) ORDER BY date"
            df = pd.read_sql_query(sql, conn, params=list(subreddits))
        else:
            df = pd.read_sql_query(
                "SELECT subreddit, date, yhat, yhat_lower, yhat_upper FROM sentiment_forecast ORDER BY date",
                conn,
            )
        conn.close()
        return df.to_dict(orient="records")
    except Exception:
        return []


def get_topics() -> List[dict]:
    try:
        conn = _connect()
        df = pd.read_sql_query(
            "SELECT topic_id, keywords, doc_count, coherence_score FROM topics WHERE topic_id != -1 ORDER BY doc_count DESC",
            conn,
        )
        conn.close()
        return df.to_dict(orient="records")
    except Exception:
        return []


def get_emerging_topics(days: int = 7) -> List[dict]:
    try:
        conn = _connect()
        df = pd.read_sql_query(
            "SELECT topic_id, keywords, doc_count FROM topics WHERE topic_id != -1 AND created_at >= datetime('now', ?) ORDER BY doc_count DESC",
            conn,
            params=[f"-{days} days"],
        )
        conn.close()
        return df.to_dict(orient="records")
    except Exception:
        return []


def get_topic_over_time(topic_id: int) -> List[dict]:
    try:
        conn = _connect()
        df = pd.read_sql_query(
            "SELECT week_start, doc_count, avg_sentiment FROM topic_over_time WHERE topic_id = ? ORDER BY week_start",
            conn,
            params=[topic_id],
        )
        conn.close()
        return df.to_dict(orient="records")
    except Exception:
        return []


def get_topic_heatmap(n: int = 30) -> List[dict]:
    try:
        conn = _connect()
        df = pd.read_sql_query(
            """
            SELECT topic_id, week_start, avg_sentiment
            FROM topic_over_time
            WHERE topic_id IN (
                SELECT topic_id FROM topics WHERE topic_id != -1
                ORDER BY doc_count DESC LIMIT ?
            )
            ORDER BY topic_id, week_start
            """,
            conn,
            params=[n],
        )
        conn.close()
        return df.to_dict(orient="records")
    except Exception:
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
            LIMIT ? OFFSET ?
        """
        params += [limit, offset]
        df = pd.read_sql_query(sql, conn, params=params)
        conn.close()
        return df.to_dict(orient="records")
    except Exception:
        return []


def get_vader_agreement() -> List[dict]:
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
            WHERE p.is_filtered = 0 AND p.clean_text IS NOT NULL
            LIMIT 10000
            """,
            conn,
        )
        conn.close()
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
        return []


def get_known_subreddits() -> List[str]:
    try:
        conn = _connect()
        rows = conn.execute(
            "SELECT DISTINCT subreddit FROM posts ORDER BY subreddit"
        ).fetchall()
        conn.close()
        return [r[0] for r in rows if r[0]]
    except Exception:
        return []


def get_date_range() -> dict:
    try:
        conn = _connect()
        row = conn.execute(
            "SELECT MIN(DATE(timestamp)), MAX(DATE(timestamp)) FROM posts"
        ).fetchone()
        conn.close()
        if row and row[0] and row[1]:
            return {"start": row[0], "end": row[1]}
    except Exception:
        pass
    today = date.today()
    return {"start": str(today - timedelta(days=30)), "end": str(today)}
