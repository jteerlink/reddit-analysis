#!/usr/bin/env python3
"""Backtest simple sentiment forecast baselines on ordered daily aggregates.

The backtest is read-only and intentionally reports persistence and recent
average baselines separately.  It does not promote a forecast model.
"""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path


def _read_daily(db_path: str) -> dict[str, list[tuple[date, float]]]:
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT subreddit, date, mean_score FROM sentiment_daily WHERE mean_score IS NOT NULL ORDER BY subreddit, date"
        ).fetchall()
    finally:
        conn.close()
    result: dict[str, list[tuple[date, float]]] = defaultdict(list)
    for subreddit, value, score in rows:
        try:
            result[str(subreddit)].append((date.fromisoformat(str(value)), float(score)))
        except (TypeError, ValueError):
            continue
    return dict(result)


def _scores(pairs: list[tuple[float, float, float | None, float | None]]) -> dict:
    errors = [actual - predicted for actual, predicted, _, _ in pairs]
    if not errors:
        return {"n": 0, "mae": None, "rmse": None, "interval_coverage": None}
    result = {
        "n": len(errors),
        "mae": sum(abs(value) for value in errors) / len(errors),
        "rmse": math.sqrt(sum(value * value for value in errors) / len(errors)),
    }
    bounded = [(actual, lower, upper) for actual, _, lower, upper in pairs if lower is not None and upper is not None]
    result["interval_coverage"] = (
        sum(lower <= actual <= upper for actual, lower, upper in bounded) / len(bounded)
        if bounded else None
    )
    return result


def backtest(series: dict[str, list[tuple[date, float]]], horizon: int = 7, min_train_days: int = 28, recent_days: int = 7, splits: int = 3, include_prophet: bool = False) -> dict:
    if min(horizon, min_train_days, recent_days, splits) < 1:
        raise ValueError("horizon, min_train_days, recent_days, and splits must be positive")
    values: dict[str, list[tuple[float, float, float | None, float | None]]] = {"persistence": [], "recent_average": []}
    if include_prophet:
        values["prophet"] = []
    prophet_error = None
    prophet = None
    if include_prophet:
        try:
            from prophet import Prophet
            prophet = Prophet
        except ImportError as exc:
            prophet_error = str(exc)
    split_details = []
    for subreddit in sorted(series):
        ordered = sorted(series[subreddit], key=lambda item: item[0])
        if len(ordered) < min_train_days + horizon:
            continue
        origins = []
        for origin in range(min_train_days, len(ordered)):
            origin_date = ordered[origin - 1][0]
            target_end = origin_date + timedelta(days=horizon)
            if any(origin_date < observed_date <= target_end for observed_date, _ in ordered[origin:]):
                origins.append(origin)
        origins = origins[-splits:]
        for origin in origins:
            origin_date = ordered[origin - 1][0]
            target_end = origin_date + timedelta(days=horizon)
            train = [(observed_date, score) for observed_date, score in ordered[:origin] if observed_date <= origin_date]
            actual_rows = [(observed_date, score) for observed_date, score in ordered[origin:] if origin_date < observed_date <= target_end]
            actual = [score for _, score in actual_rows]
            persistence = train[-1][1]
            recent_values = [score for observed_date, score in train if observed_date > origin_date - timedelta(days=recent_days)]
            recent = sum(recent_values) / len(recent_values) if recent_values else persistence
            values["persistence"].extend((score, persistence, None, None) for score in actual)
            values["recent_average"].extend((score, recent, None, None) for score in actual)
            if prophet and actual_rows:
                try:
                    import pandas as pd
                    model = prophet(daily_seasonality=False, weekly_seasonality=True, yearly_seasonality=False, interval_width=0.95)
                    model.fit(pd.DataFrame({"ds": [item[0] for item in train], "y": [item[1] for item in train]}))
                    forecast = model.predict(pd.DataFrame({"ds": [item[0] for item in actual_rows]}))
                    values["prophet"].extend(
                        (actual_value, float(prediction.yhat), float(prediction.yhat_lower), float(prediction.yhat_upper))
                        for actual_value, prediction in zip(actual, forecast.itertuples())
                    )
                except Exception as exc:  # a single failed origin must not hide baseline results
                    prophet_error = str(exc)
            split_details.append({"subreddit": subreddit, "training_through": origin_date.isoformat(), "target_start": (origin_date + timedelta(days=1)).isoformat(), "target_end": target_end.isoformat(), "n_observed": len(actual)})

    metrics = {}
    for name, pairs in values.items():
        metrics[name] = _scores(pairs)
    winner = None
    if metrics["persistence"]["mae"] is not None and metrics["recent_average"]["mae"] is not None:
        winner = min(("persistence", "recent_average"), key=lambda name: metrics[name]["mae"])
    return {
        "status": "complete" if split_details else "insufficient_data",
        "horizon_days": horizon,
        "minimum_training_days": min_train_days,
        "recent_average_days": recent_days,
        "splits_requested": splits,
        "splits": split_details,
        "prophet_requested": include_prophet,
        "prophet_error": prophet_error,
        "metrics": metrics,
        "selected_baseline": winner,
        "promotion": {"eligible": False, "reason": "baseline comparison only; forecast promotion requires held-out model intervals"},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="historical_reddit_data.db", help="SQLite database path")
    parser.add_argument("--horizon", type=int, default=7, help="Forecast horizon in days")
    parser.add_argument("--min-train-days", type=int, default=28)
    parser.add_argument("--recent-days", type=int, default=7)
    parser.add_argument("--splits", type=int, default=3)
    parser.add_argument("--prophet", action="store_true", help="Fit Prophet in memory on each train split for comparison")
    parser.add_argument("--output", default="data/forecast_backtest.json")
    args = parser.parse_args()
    if not Path(args.db).exists():
        parser.error(f"database not found: {args.db}")
    result = backtest(_read_daily(args.db), args.horizon, args.min_train_days, args.recent_days, args.splits, args.prophet)
    result["database"] = str(args.db)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
