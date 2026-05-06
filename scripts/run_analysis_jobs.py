#!/usr/bin/env python
"""Run persisted analysis artifact backfills."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.analysis.jobs import run_analysis_backfill
from src.ml.db import get_connection


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Reddit Analyzer intelligence artifact jobs")
    parser.add_argument("--db", default="historical_reddit_data.db")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.dry_run:
        print("analysis jobs dry-run: schema and artifact backfill would run")
        return 0

    conn = get_connection(args.db)
    try:
        result = run_analysis_backfill(conn)
    finally:
        conn.close()
    for key, value in result.items():
        print(f"{key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
