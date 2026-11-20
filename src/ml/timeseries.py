"""
ML Layer — Time Series Analysis

Aggregates daily sentiment, detects change points with PELT, generates Prophet
forecasts, and computes topic-specific sentiment trends. Results are written
back to SQLite so the dashboard can read them directly.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

import pandas as pd

from src.db.connection import is_postgres_connection
from src.ml.db import (
    ensure_timeseries_tables,
    get_connection,
    replace_timeseries_results,
)

logger = logging.getLogger(__name__)

# Sentiment label → numeric score used for aggregation
_LABEL_SCORE: Dict[str, float] = {"positive": 1.0, "neutral": 0.0, "negative": -1.0}
_FORECAST_COLUMNS = [
    "subreddit",
    "date",
    "yhat",
    "yhat_lower",
    "yhat_upper",
    "generated_at",
    "training_through",
    "interval_width",
]
_FORECAST_INTERVAL_WIDTH = 0.95


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
        observed = pd.Series(
            grp["mean_score"].to_numpy(),
            index=pd.DatetimeIndex(pd.to_datetime(grp["date"])),
        )
        for days, suffix in ((7, "7d"), (30, "30d")):
            rolling = observed.rolling(f"{days}D", min_periods=1, closed="right")
            grp[f"rolling_{suffix}"] = rolling.mean().to_numpy()
            grp[f"observed_days_{suffix}"] = rolling.count().to_numpy()
        frames.append(
            grp[
                [
                    "subreddit",
                    "date",
                    "rolling_7d",
                    "rolling_30d",
                    "observed_days_7d",
                    "observed_days_30d",
                ]
            ]
        )
    if not frames:
        return pd.DataFrame(
            columns=[
                "subreddit",
                "date",
                "rolling_7d",
                "rolling_30d",
                "observed_days_7d",
                "observed_days_30d",
            ]
        )
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
            # ruptures reports exclusive, one-based segment ends. The final
            # value is the terminal boundary and has no following segment.
            idx = int(bp)
            if idx <= 0 or idx >= len(signal):
                continue
            before = signal[max(0, idx - 3) : idx].mean()
            after = signal[idx : min(len(signal), idx + 3)].mean()
            magnitude = float(after - before)
            if not pd.notna(magnitude) or abs(magnitude) < 1e-12:
                continue
            records.append(
                {
                    "subreddit": sub,
                    "date": dates[idx],
                    "magnitude": magnitude,
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
        return pd.DataFrame(columns=_FORECAST_COLUMNS)

    frames = []
    generated_at = datetime.now(timezone.utc).isoformat()
    for sub, grp in daily.groupby("subreddit"):
        grp = grp.sort_values("date")[["date", "mean_score"]].rename(
            columns={"date": "ds", "mean_score": "y"}
        )
        if len(grp) < 7:
            logger.info("Skipping %s — fewer than 7 data points", sub)
            continue

        grp["ds"] = pd.to_datetime(grp["ds"])
        m = Prophet(
            daily_seasonality=False,
            weekly_seasonality=True,
            yearly_seasonality=False,
            interval_width=_FORECAST_INTERVAL_WIDTH,
        )
        # Silence Prophet's verbose logging
        import logging as _logging

        _logging.getLogger("prophet").setLevel(_logging.WARNING)
        _logging.getLogger("cmdstanpy").setLevel(_logging.WARNING)

        m.fit(grp)
        future = m.make_future_dataframe(periods=forecast_days)
        forecast = m.predict(future)

        forecast["ds"] = pd.to_datetime(forecast["ds"])
        cutoff = grp["ds"].max()
        horizon_end = cutoff + pd.Timedelta(days=forecast_days)
        future_only = forecast[
            (forecast["ds"] > cutoff) & (forecast["ds"] <= horizon_end)
        ][["ds", "yhat", "yhat_lower", "yhat_upper"]].copy()
        future_only["subreddit"] = sub
        future_only["date"] = future_only["ds"].dt.strftime("%Y-%m-%d")
        future_only["generated_at"] = generated_at
        future_only["training_through"] = grp["ds"].max().strftime("%Y-%m-%d")
        future_only["interval_width"] = _FORECAST_INTERVAL_WIDTH
        frames.append(future_only[_FORECAST_COLUMNS])

    if not frames:
        return pd.DataFrame(columns=_FORECAST_COLUMNS)
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
        observed = pd.Series(
            grp["mean_sentiment"].to_numpy(),
            index=pd.DatetimeIndex(pd.to_datetime(grp["date"])),
        )
        grp["rolling_7d"] = (
            observed.rolling("7D", min_periods=1, closed="right").mean().to_numpy()
        )
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

    if days < 1 or forecast_days < 1:
        conn.close()
        raise ValueError("days and forecast_days must be positive")
    # Include warm-up history so the first displayed average has a full window.
    scope_start = (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()
    daily_history = _aggregate_daily_sentiment(conn, days + 30)
    if daily_history.empty:
        daily = moving_avg = change_pts = forecast = topic_trends = pd.DataFrame()
    else:
        daily = daily_history[daily_history["date"].astype(str) >= scope_start]
        moving_avg = _compute_moving_averages(daily_history)
        moving_avg = moving_avg[moving_avg["date"].astype(str) >= scope_start]
        change_pts = _detect_change_points(daily_history)
        change_pts = change_pts[change_pts["date"].astype(str) >= scope_start]
        forecast = _run_prophet_forecast(daily, forecast_days)
        topic_trends = _compute_topic_sentiment_trends(conn, days + 30)
        topic_trends = topic_trends[topic_trends["date"].astype(str) >= scope_start]
    # Compute everything before atomically replacing this run's derived scope.
    replace_timeseries_results(
        conn,
        scope_start,
        {
            "sentiment_daily": daily,
            "sentiment_moving_avg": moving_avg,
            "change_points": change_pts,
            "sentiment_forecast": forecast,
            "topic_sentiment_trends": topic_trends,
        },
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
