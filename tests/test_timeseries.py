"""Regression tests for calendar windows, PELT boundaries, and forecast runs."""

import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.ml.db import ensure_timeseries_tables, replace_timeseries_results
from src.ml.timeseries import (
    _compute_moving_averages,
    _detect_change_points,
    _run_prophet_forecast,
)


def test_moving_average_uses_calendar_days_and_reports_observed_days():
    daily = pd.DataFrame(
        {
            "subreddit": ["r/test", "r/test"],
            "date": ["2026-01-01", "2026-02-01"],
            "mean_score": [1.0, -1.0],
        }
    )

    result = _compute_moving_averages(daily).set_index("date")

    assert result.loc["2026-02-01", "rolling_7d"] == -1.0
    assert result.loc["2026-02-01", "observed_days_7d"] == 1.0
    assert result.loc["2026-02-01", "observed_days_30d"] == 1.0


def test_pelt_uses_next_segment_date_and_skips_terminal_and_zero_boundaries():
    class FakePelt:
        def __init__(self, **kwargs):
            del kwargs

        def fit(self, signal):
            assert len(signal) == 6
            return self

        def predict(self, pen):
            assert pen == 1.0
            return [3, 6]

    fake_ruptures = SimpleNamespace(Pelt=FakePelt)
    daily = pd.DataFrame(
        {
            "subreddit": ["r/test"] * 6,
            "date": pd.date_range("2026-01-01", periods=6).strftime("%Y-%m-%d"),
            "mean_score": [0.0, 0.0, 0.0, 1.0, 1.0, 1.0],
        }
    )

    with patch.dict(sys.modules, {"ruptures": fake_ruptures}):
        result = _detect_change_points(daily)

    assert result.to_dict("records") == [
        {"subreddit": "r/test", "date": "2026-01-04", "magnitude": 1.0}
    ]


def test_pelt_constant_series_has_no_shift():
    class FakePelt:
        def __init__(self, **kwargs):
            del kwargs

        def fit(self, signal):
            return self

        def predict(self, pen):
            del pen
            return [3, 6]

    daily = pd.DataFrame(
        {
            "subreddit": ["r/test"] * 6,
            "date": pd.date_range("2026-01-01", periods=6).strftime("%Y-%m-%d"),
            "mean_score": [0.0] * 6,
        }
    )
    with patch.dict(sys.modules, {"ruptures": SimpleNamespace(Pelt=FakePelt)}):
        result = _detect_change_points(daily)

    assert result.empty


def test_forecast_has_configured_horizon_and_run_metadata():
    class FakeProphet:
        instances = []

        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.train = None
            self.instances.append(self)

        def fit(self, train):
            self.train = train.copy()
            return self

        def make_future_dataframe(self, periods):
            # Include extra rows to prove the persisted horizon is bounded.
            return pd.DataFrame(
                {
                    "ds": pd.date_range(
                        self.train["ds"].min(),
                        periods=len(self.train) + periods + 2,
                        freq="D",
                    )
                }
            )

        def predict(self, future):
            return pd.DataFrame(
                {
                    "ds": future["ds"],
                    "yhat": 0.1,
                    "yhat_lower": -0.2,
                    "yhat_upper": 0.4,
                }
            )

    fake_prophet = SimpleNamespace(Prophet=FakeProphet)
    daily = pd.DataFrame(
        {
            "subreddit": ["r/test"] * 7,
            "date": pd.date_range("2026-01-01", periods=7).strftime("%Y-%m-%d"),
            "mean_score": [0.0, 1.0, 0.0, 1.0, 0.0, 1.0, 0.0],
        }
    )

    with patch.dict(sys.modules, {"prophet": fake_prophet}):
        result = _run_prophet_forecast(daily, forecast_days=3)

    assert len(result) == 3
    assert result["date"].tolist() == ["2026-01-08", "2026-01-09", "2026-01-10"]
    assert result["generated_at"].nunique() == 1
    assert result["training_through"].unique().tolist() == ["2026-01-07"]
    assert result["interval_width"].unique().tolist() == [0.95]
    assert FakeProphet.instances[0].kwargs["interval_width"] == 0.95


def test_replace_timeseries_results_removes_stale_scope_and_prior_forecast(tmp_path):
    conn = sqlite3.connect(tmp_path / "timeseries.db")
    ensure_timeseries_tables(conn)
    conn.execute(
        "INSERT INTO sentiment_daily VALUES (?, ?, ?, ?, ?, ?)",
        ("r/test", "2026-01-01", 1.0, 1, 0, 0),
    )
    conn.execute(
        "INSERT INTO sentiment_daily VALUES (?, ?, ?, ?, ?, ?)",
        ("r/test", "2026-01-20", 1.0, 1, 0, 0),
    )
    conn.execute(
        "INSERT INTO change_points VALUES (?, ?, ?)",
        ("r/test", "2026-01-20", 1.0),
    )
    conn.execute(
        "INSERT INTO sentiment_forecast "
        "(subreddit, date, yhat, yhat_lower, yhat_upper, generated_at, "
        "training_through, interval_width) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("r/test", "2026-01-21", 1.0, 0.0, 2.0, "old", "2026-01-20", 0.8),
    )
    conn.commit()

    results = {
        "sentiment_daily": pd.DataFrame(
            [("r/test", "2026-01-20", -1.0, 0, 0, 1)],
            columns=[
                "subreddit",
                "date",
                "mean_score",
                "pos_count",
                "neu_count",
                "neg_count",
            ],
        ),
        "sentiment_moving_avg": pd.DataFrame(
            [("r/test", "2026-01-20", -1.0, -1.0, 1, 1)],
            columns=[
                "subreddit",
                "date",
                "rolling_7d",
                "rolling_30d",
                "observed_days_7d",
                "observed_days_30d",
            ],
        ),
        "change_points": pd.DataFrame(columns=["subreddit", "date", "magnitude"]),
        "sentiment_forecast": pd.DataFrame(
            [("r/test", "2026-01-22", 0.2, -0.1, 0.5, "new", "2026-01-20", 0.95)],
            columns=[
                "subreddit",
                "date",
                "yhat",
                "yhat_lower",
                "yhat_upper",
                "generated_at",
                "training_through",
                "interval_width",
            ],
        ),
        "topic_sentiment_trends": pd.DataFrame(
            columns=["topic_id", "date", "mean_sentiment", "rolling_7d"]
        ),
    }

    replace_timeseries_results(conn, "2026-01-10", results)

    assert conn.execute(
        "SELECT date FROM sentiment_daily ORDER BY date"
    ).fetchall() == [
        ("2026-01-01",),
        ("2026-01-20",),
    ]
    assert conn.execute("SELECT COUNT(*) FROM change_points").fetchone()[0] == 0
    forecast = conn.execute(
        "SELECT date, generated_at, training_through, interval_width "
        "FROM sentiment_forecast"
    ).fetchone()
    assert tuple(forecast) == ("2026-01-22", "new", "2026-01-20", 0.95)
    conn.close()
