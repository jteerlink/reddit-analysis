#!/usr/bin/env python3
"""Run time series analysis on collected Reddit sentiment data."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.ml.timeseries import run_timeseries_analysis


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Aggregate sentiment, detect change points, and forecast trends."
    )
    parser.add_argument(
        "--db", default="historical_reddit_data.db", help="Path to SQLite database"
    )
    parser.add_argument(
        "--days", type=int, default=90, help="Rolling window in days (default: 90)"
    )
    parser.add_argument(
        "--forecast-days",
        type=int,
        default=14,
        help="Number of days to forecast ahead (default: 14)",
    )
    parser.add_argument(
        "--no-mlflow", action="store_true", help="Disable MLflow experiment tracking"
    )
    args = parser.parse_args()

    if not Path(args.db).exists():
        print(f"Error: database not found at {args.db}", file=sys.stderr)
        sys.exit(1)

    result = run_timeseries_analysis(
        db_path=args.db,
        days=args.days,
        forecast_days=args.forecast_days,
        mlflow_tracking=not args.no_mlflow,
    )

    gate = "PASSED" if result["gate_passed"] else "FAILED"

    print("=" * 50)
    print("Time Series Analysis Complete")
    print(f"Daily sentiment rows:    {result['daily_rows']:,}")
    print(f"Moving average rows:     {result['moving_avg_rows']:,}")
    print(f"Change points detected:  {result['change_point_rows']:,}")
    print(f"Forecast rows:           {result['forecast_rows']:,}")
    print(f"Topic trend rows:        {result['topic_trend_rows']:,}")
    print(f"Gate:                    {gate} (forecast generated)")
    print(f"Window:                  {args.days} days")
    print(f"Forecast horizon:        {args.forecast_days} days")
    print("=" * 50)

    if not result["gate_passed"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
