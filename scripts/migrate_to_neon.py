#!/usr/bin/env python3
"""Migrate the runtime SQLite database to Neon PostgreSQL."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import pandas as pd
from dateutil import parser as date_parser

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = PROJECT_ROOT / "scripts" / "neon_schema.sql"

MIGRATION_ORDER = [
    "posts",
    "comments",
    "preprocessed",
    "sentiment_predictions",
    "api_metrics",
    "collection_metadata",
    "batch_collections",
    "topics",
    "topic_assignments",
    "topic_over_time",
    "sentiment_daily",
    "sentiment_moving_avg",
    "change_points",
    "sentiment_forecast",
    "topic_sentiment_trends",
]

EXCLUDED_TABLES = [
    "posts_other",
    "comments_other",
    "embedding_2d",
    "cluster_labels",
    "narrative_events",
]

DATE_COLUMNS = {
    "topic_over_time": ["week_start"],
    "sentiment_daily": ["date"],
    "sentiment_moving_avg": ["date"],
    "change_points": ["date"],
    "sentiment_forecast": ["date"],
    "topic_sentiment_trends": ["date"],
}

TIMESTAMP_COLUMNS = {
    "posts": ["timestamp", "created_at"],
    "comments": ["timestamp", "created_at"],
    "api_metrics": ["timestamp"],
    "collection_metadata": ["collection_timestamp", "created_at"],
    "batch_collections": [
        "collection_timestamp",
        "storage_timestamp",
        "created_at",
    ],
    "preprocessed": ["processed_at"],
    "sentiment_predictions": ["predicted_at"],
    "topics": ["created_at"],
    "topic_assignments": ["assigned_at"],
}


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name = ?", (table,)
    ).fetchone()
    return row is not None


def _source_count(conn: sqlite3.Connection, table: str) -> int:
    if not _table_exists(conn, table):
        return 0
    return int(conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])


def _parse_timestamp(value: Any) -> datetime | None:
    if value is None or pd.isna(value):
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        dt = date_parser.parse(str(value))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _parse_date(value: Any) -> date | None:
    if value is None or pd.isna(value):
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    return date_parser.parse(str(value)).date()


def _parse_json(value: Any) -> Any:
    if value is None or pd.isna(value):
        return None
    if isinstance(value, (list, dict)):
        return value
    return json.loads(value)


def _transform(table: str, df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    df = df.copy()
    for column in TIMESTAMP_COLUMNS.get(table, []):
        if column in df.columns:
            df[column] = df[column].map(_parse_timestamp)
    for column in DATE_COLUMNS.get(table, []):
        if column in df.columns:
            df[column] = df[column].map(_parse_date)
    if table == "preprocessed" and "is_filtered" in df.columns:
        df["is_filtered"] = df["is_filtered"].map(bool)
    if table == "sentiment_predictions" and "logits" in df.columns:
        df["logits"] = df["logits"].map(_parse_json)
    return df.where(pd.notna(df), None)


def _iter_batches(df: pd.DataFrame, size: int) -> Iterable[pd.DataFrame]:
    for start in range(0, len(df), size):
        yield df.iloc[start : start + size]


def _load_psycopg2():
    try:
        import psycopg2
        from psycopg2.extras import Json, execute_values
    except ImportError as exc:
        raise RuntimeError("psycopg2-binary is required for live migration") from exc
    return psycopg2, Json, execute_values


def _row_values(table: str, batch: pd.DataFrame, json_adapter) -> list[tuple]:
    rows = []
    for values in batch.itertuples(index=False, name=None):
        if table == "sentiment_predictions" and "logits" in batch.columns:
            values = list(values)
            logits_idx = list(batch.columns).index("logits")
            if values[logits_idx] is not None:
                values[logits_idx] = json_adapter(values[logits_idx])
            values = tuple(values)
        rows.append(values)
    return rows


def _insert_batch(pg_conn, table: str, batch: pd.DataFrame, execute_values, json_adapter) -> None:
    columns = list(batch.columns)
    quoted_columns = ", ".join(f'"{col}"' for col in columns)
    sql = f'INSERT INTO "{table}" ({quoted_columns}) VALUES %s ON CONFLICT DO NOTHING'
    rows = _row_values(table, batch, json_adapter)
    with pg_conn.cursor() as cursor:
        execute_values(cursor, sql, rows, page_size=len(rows))


def _target_count(pg_conn, table: str) -> int:
    with pg_conn.cursor() as cursor:
        cursor.execute(f'SELECT COUNT(*) FROM "{table}"')
        return int(cursor.fetchone()[0])


def run(args: argparse.Namespace) -> int:
    source = Path(args.source)
    if not source.exists():
        print(f"Source SQLite database not found: {source}", file=sys.stderr)
        return 1

    with sqlite3.connect(source) as sqlite_conn:
        print("Runtime tables selected for Neon v1:")
        for table in MIGRATION_ORDER:
            print(f"  {table}: {_source_count(sqlite_conn, table)} row(s)")
        present_excluded = [
            table for table in EXCLUDED_TABLES if _table_exists(sqlite_conn, table)
        ]
        if present_excluded:
            print(
                "Tables excluded from v1 because runtime code does not reference them: "
                + ", ".join(present_excluded)
            )

        if args.dry_run:
            print("Dry run complete; no Neon writes performed.")
            return 0

        database_url = args.database_url or os.environ.get("DATABASE_URL")
        if not database_url:
            print("DATABASE_URL or --database-url is required for live migration.", file=sys.stderr)
            return 1

        psycopg2, Json, execute_values = _load_psycopg2()
        pg_conn = psycopg2.connect(database_url)
        try:
            if args.create_schema:
                schema_sql = Path(args.schema).read_text()
                with pg_conn.cursor() as cursor:
                    cursor.execute(schema_sql)
                pg_conn.commit()
                print(f"Schema applied from {args.schema}")

            for table in MIGRATION_ORDER:
                if not _table_exists(sqlite_conn, table):
                    print(f"{table}: missing in source, skipped")
                    continue
                df = pd.read_sql_query(f'SELECT * FROM "{table}"', sqlite_conn)
                df = _transform(table, df)
                for batch in _iter_batches(df, args.batch_size):
                    if not batch.empty:
                        _insert_batch(pg_conn, table, batch, execute_values, Json)
                pg_conn.commit()
                print(
                    f"{table}: source={len(df)} target={_target_count(pg_conn, table)}"
                )
        finally:
            pg_conn.close()
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate SQLite Reddit data to Neon")
    parser.add_argument("--source", default="historical_reddit_data.db")
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--schema", default=str(SCHEMA_PATH))
    parser.add_argument("--batch-size", type=int, default=1000)
    parser.add_argument("--create-schema", action="store_true", default=False)
    parser.add_argument("--dry-run", action="store_true", default=False)
    raise SystemExit(run(parser.parse_args()))


if __name__ == "__main__":
    main()
