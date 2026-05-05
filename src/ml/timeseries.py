"""
ML Layer — Time Series Analysis

Aggregates daily sentiment, detects change points with PELT, generates Prophet
forecasts, and computes topic-specific sentiment trends. Results are written
back to SQLite so the dashboard can read them directly.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

import pandas as pd

from src.db.connection import is_postgres_connection
from src.ml.db import (
    ensure_timeseries_tables,
    get_connection,
    upsert_change_points,
    upsert_sentiment_daily,
    upsert_sentiment_forecast,
    upsert_sentiment_moving_avg,
    upsert_topic_sentiment_trends,
)

logger = logging.getLogger(__name__)

# Sentiment label → numeric score used for aggregation
_LABEL_SCORE: Dict[str, float] = {"positive": 1.0, "neutral": 0.0, "negative": -1.0}


# ---------------------------------------------------------------------------
# 1. Daily sentiment aggregation
# ---------------------------------------------------------------------------


def _aggregate_daily_sentiment(conn: Any, days: int) -> pd.DataFrame:
    """
    Return a DataFrame with one row per (subreddit, date).

    Joins `sentiment_predictions` → `preprocessed` → posts/comments to pick
    up the subreddit and the original Reddit timestamp.
    """
    where_recent = (
        f"COALESCE(po.timestamp, co.timestamp) >= NOW() - INTERVAL '{int(days)} days'"
        if is_postgres_connection(conn)
        else "COALESCE(po.timestamp, co.timestamp) >= datetime('now', ?)"
    )
    params = () if is_postgres_connection(conn) else (f"-{days} days",)
    query = f"""
        SELECT
            COALESCE(po.subreddit, co.subreddit)              AS subreddit,
            DATE(COALESCE(po.timestamp, co.timestamp))        AS date,
            sp.label,
            sp.confidence
        FROM sentiment_predictions sp
        JOIN preprocessed p ON sp.id = p.id
        LEFT JOIN posts    po ON p.id = po.id AND p.content_type = 'post'
        LEFT JOIN comments co ON p.id = co.id AND p.content_type = 'comment'
        WHERE {where_recent}
          AND sp.label IS NOT NULL
    """
    df = pd.read_sql_query(query, conn, params=params)
    if df.empty:
        return df

    df["score"] = df["label"].map(_LABEL_SCORE).fillna(0.0)
    agg = (
        df.groupby(["subreddit", "date"])
        .agg(
            mean_score=("score", "mean"),
            pos_count=("label", lambda s: (s == "positive").sum()),
            neu_count=("label", lambda s: (s == "neutral").sum()),
            neg_count=("label", lambda s: (s == "negative").sum()),
        )
        .reset_index()
    )
    return agg


def _compute_moving_averages(daily: pd.DataFrame) -> pd.DataFrame:
    """Add 7-day and 30-day rolling averages per subreddit."""
    frames = []
    for _, grp in daily.groupby("subreddit"):
        grp = grp.sort_values("date").copy()
        grp["rolling_7d"] = grp["mean_score"].rolling(7, min_periods=1).mean()
        grp["rolling_30d"] = grp["mean_score"].rolling(30, min_periods=1).mean()
        frames.append(grp[["subreddit", "date", "rolling_7d", "rolling_30d"]])
    if not frames:
        return pd.DataFrame(columns=["subreddit", "date", "rolling_7d", "rolling_30d"])
    return pd.concat(frames, ignore_index=True)


# ---------------------------------------------------------------------------
# 2. Change point detection (PELT)
# ---------------------------------------------------------------------------


def _detect_change_points(daily: pd.DataFrame) -> pd.DataFrame:
    """
    Run PELT per subreddit on the daily mean_score series.

    Returns a DataFrame with columns (subreddit, date, magnitude).
    """
    try:
        import ruptures as rpt
    except ImportError:
        logger.warning("ruptures not installed — skipping change point detection")
        return pd.DataFrame(columns=["subreddit", "date", "magnitude"])

    records = []
    for sub, grp in daily.groupby("subreddit"):
        grp = grp.sort_values("date").reset_index(drop=True)
        signal = grp["mean_score"].values.astype(float)
        if len(signal) < 4:
            continue

        algo = rpt.Pelt(model="rbf").fit(signal)
        try:
            breakpoints = algo.predict(pen=1.0)
        except Exception:
            continue

        dates = grp["date"].tolist()
        for bp in breakpoints:
            idx = bp - 1  # ruptures returns 1-based end indices
            if idx <= 0 or idx >= len(signal):
                continue
            before = signal[max(0, idx - 3) : idx].mean()
            after = signal[idx : min(len(signal), idx + 3)].mean()
            records.append(
                {
                    "subreddit": sub,
                    "date": dates[idx],
                    "magnitude": float(after - before),
                }
            )

    if not records:
        return pd.DataFrame(columns=["subreddit", "date", "magnitude"])
    return pd.DataFrame(records)


# ---------------------------------------------------------------------------
# 3. Prophet forecast
# ---------------------------------------------------------------------------


def _run_prophet_forecast(daily: pd.DataFrame, forecast_days: int) -> pd.DataFrame:
    """
    Fit Prophet per subreddit and forecast `forecast_days` into the future.

    Returns rows only for future dates (yhat, yhat_lower, yhat_upper).
    """
    try:
        from prophet import Prophet
    except ImportError:
        logger.warning("prophet not installed — skipping forecasting")
        return pd.DataFrame(columns=["subreddit", "date", "yhat", "yhat_lower", "yhat_upper"])

    frames = []
    for sub, grp in daily.groupby("subreddit"):
        grp = grp.sort_values("date")[["date", "mean_score"]].rename(
            columns={"date": "ds", "mean_score": "y"}
        )
        if len(grp) < 7:
            logger.info("Skipping %s — fewer than 7 data points", sub)
            continue

        m = Prophet(daily_seasonality=False, weekly_seasonality=True, yearly_seasonality=False)
        # Silence Prophet's verbose logging
        import logging as _logging
        _logging.getLogger("prophet").setLevel(_logging.WARNING)
        _logging.getLogger("cmdstanpy").setLevel(_logging.WARNING)

        m.fit(grp)
        future = m.make_future_dataframe(periods=forecast_days)
        forecast = m.predict(future)

        future_only = forecast[forecast["ds"] > grp["ds"].max()][
            ["ds", "yhat", "yhat_lower", "yhat_upper"]
        ].copy()
        future_only["subreddit"] = sub
        future_only["date"] = future_only["ds"].dt.strftime("%Y-%m-%d")
        frames.append(
            future_only[["subreddit", "date", "yhat", "yhat_lower", "yhat_upper"]]
        )

    if not frames:
        return pd.DataFrame(columns=["subreddit", "date", "yhat", "yhat_lower", "yhat_upper"])
    return pd.concat(frames, ignore_index=True)


# ---------------------------------------------------------------------------
# 4. Topic-specific sentiment trends
# ---------------------------------------------------------------------------


def _compute_topic_sentiment_trends(conn: Any, days: int) -> pd.DataFrame:
    """
    Join topic_assignments → sentiment_predictions → posts/comments to get
    daily mean sentiment per topic, then compute a 7-day rolling average.
    """
    where_recent = (
        f"COALESCE(po.timestamp, co.timestamp) >= NOW() - INTERVAL '{int(days)} days'"
        if is_postgres_connection(conn)
        else "COALESCE(po.timestamp, co.timestamp) >= datetime('now', ?)"
    )
    params = () if is_postgres_connection(conn) else (f"-{days} days",)
    query = f"""
        SELECT
            ta.topic_id,
            DATE(COALESCE(po.timestamp, co.timestamp)) AS date,
            sp.label
        FROM topic_assignments ta
        JOIN sentiment_predictions sp ON ta.id = sp.id
        JOIN preprocessed p ON ta.id = p.id
        LEFT JOIN posts    po ON p.id = po.id AND p.content_type = 'post'
        LEFT JOIN comments co ON p.id = co.id AND p.content_type = 'comment'
        WHERE {where_recent}
          AND sp.label IS NOT NULL
          AND ta.topic_id >= 0
    """
    df = pd.read_sql_query(query, conn, params=params)
    if df.empty:
        return pd.DataFrame(
            columns=["topic_id", "date", "mean_sentiment", "rolling_7d"]
        )

    df["score"] = df["label"].map(_LABEL_SCORE).fillna(0.0)
    daily = (
        df.groupby(["topic_id", "date"])["score"]
        .mean()
        .reset_index()
        .rename(columns={"score": "mean_sentiment"})
    )

    frames = []
    for _, grp in daily.groupby("topic_id"):
        grp = grp.sort_values("date").copy()
        grp["rolling_7d"] = grp["mean_sentiment"].rolling(7, min_periods=1).mean()
        frames.append(grp)

    if not frames:
        return pd.DataFrame(
            columns=["topic_id", "date", "mean_sentiment", "rolling_7d"]
        )
    return pd.concat(frames, ignore_index=True)


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def run_timeseries_analysis(
    db_path: str,
    days: int = 90,
    forecast_days: int = 14,
    mlflow_tracking: bool = False,
) -> Dict[str, Any]:
    """
    Run the full time series pipeline and persist results to SQLite.

    Returns a summary dict:
        daily_rows, moving_avg_rows, change_point_rows,
        forecast_rows, topic_trend_rows, gate_passed
    """
    conn = get_connection(db_path)
    ensure_timeseries_tables(conn)

    # ---- daily aggregation ----
    logger.info("Aggregating daily sentiment (last %d days)…", days)
    daily = _aggregate_daily_sentiment(conn, days)
    if daily.empty:
        logger.warning("No sentiment data found — aborting timeseries analysis")
        conn.close()
        return {
            "daily_rows": 0,
            "moving_avg_rows": 0,
            "change_point_rows": 0,
            "forecast_rows": 0,
            "topic_trend_rows": 0,
            "gate_passed": False,
        }

    upsert_sentiment_daily(
        conn,
        list(
            daily[["subreddit", "date", "mean_score", "pos_count", "neu_count", "neg_count"]]
            .itertuples(index=False, name=None)
        ),
    )

    # ---- moving averages ----
    logger.info("Computing moving averages…")
    moving_avg = _compute_moving_averages(daily)
    upsert_sentiment_moving_avg(
        conn,
        list(
            moving_avg[["subreddit", "date", "rolling_7d", "rolling_30d"]].itertuples(
                index=False, name=None
            )
        ),
    )

    # ---- change points ----
    logger.info("Detecting change points with PELT…")
    change_pts = _detect_change_points(daily)
    if not change_pts.empty:
        upsert_change_points(
            conn,
            list(
                change_pts[["subreddit", "date", "magnitude"]].itertuples(
                    index=False, name=None
                )
            ),
        )

    # ---- Prophet forecast ----
    logger.info("Fitting Prophet models (forecast_days=%d)…", forecast_days)
    forecast = _run_prophet_forecast(daily, forecast_days)
    if not forecast.empty:
        upsert_sentiment_forecast(
            conn,
            list(
                forecast[["subreddit", "date", "yhat", "yhat_lower", "yhat_upper"]].itertuples(
                    index=False, name=None
                )
            ),
        )

    # ---- topic sentiment trends ----
    logger.info("Computing topic-specific sentiment trends…")
    topic_trends = _compute_topic_sentiment_trends(conn, days)
    if not topic_trends.empty:
        upsert_topic_sentiment_trends(
            conn,
            list(
                topic_trends[["topic_id", "date", "mean_sentiment", "rolling_7d"]].itertuples(
                    index=False, name=None
                )
            ),
        )

    # ---- MLflow ----
    summary = {
        "daily_rows": len(daily),
        "moving_avg_rows": len(moving_avg),
        "change_point_rows": len(change_pts),
        "forecast_rows": len(forecast),
        "topic_trend_rows": len(topic_trends),
        "gate_passed": not forecast.empty,
    }

    if mlflow_tracking:
        try:
            import mlflow

            with mlflow.start_run(run_name="timeseries_analysis"):
                mlflow.log_param("days", days)
                mlflow.log_param("forecast_days", forecast_days)
                for k, v in summary.items():
                    if isinstance(v, (int, float)):
                        mlflow.log_metric(k, v)
        except Exception as exc:
            logger.warning("MLflow logging failed: %s", exc)

    conn.close()
    logger.info("Time series analysis complete: %s", summary)
    return summary
