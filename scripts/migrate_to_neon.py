#!/usr/bin/env python3
"""Migrate the runtime SQLite database to Neon PostgreSQL."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import pandas as pd
from dateutil import parser as date_parser

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
SCHEMA_PATH = PROJECT_ROOT / "scripts" / "neon_schema.sql"
SEED_PATH = PROJECT_ROOT / "scripts" / "seed_subreddit_categories.sql"
DEFAULT_BATCH_SIZE = 250
INSERT_PAGE_SIZE = 100
MAX_SINGLE_ROW_RETRIES = 3

MIGRATION_ORDER = [
    "posts",
    "comments",
    "preprocessed",
    "sentiment_predictions",
    "sentiment_model_active",
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
    "analysis_schema_version",
    "llm_model_registry",
    "analysis_runs",
    "analysis_artifacts",
    "artifact_status_history",
    "embedding_2d",
    "cluster_labels",
    "narrative_events",
]

EXCLUDED_TABLES = [
    "posts_other",
    "comments_other",
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
    "analysis_schema_version": ["applied_at"],
    "llm_model_registry": ["discovered_at"],
    "analysis_runs": [
        "lease_expires_at",
        "started_at",
        "finished_at",
        "created_at",
        "updated_at",
    ],
    "analysis_artifacts": [
        "freshness_timestamp",
        "lease_expires_at",
        "retry_after",
        "created_at",
        "updated_at",
    ],
    "artifact_status_history": ["created_at"],
    "narrative_events": ["created_at"],
}

JSON_COLUMNS = {
    "sentiment_predictions": ["logits"],
    "llm_model_registry": ["metadata"],
    "analysis_artifacts": ["payload"],
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
    if value is None or pd.isna(value) or str(value).strip() == "":
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        dt = date_parser.parse(str(value))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _parse_date(value: Any) -> date | None:
    if value is None or pd.isna(value) or str(value).strip() == "":
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    return date_parser.parse(str(value)).date()


def _parse_json(value: Any) -> Any:
    if value is None or pd.isna(value) or str(value).strip() == "":
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
    for column in JSON_COLUMNS.get(table, []):
        if column in df.columns:
            df[column] = df[column].map(_parse_json)
    return df.astype(object).where(pd.notna(df), None)


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
        json_columns = [
            column for column in JSON_COLUMNS.get(table, []) if column in batch.columns
        ]
        if json_columns:
            values = list(values)
            columns = list(batch.columns)
            for column in json_columns:
                json_idx = columns.index(column)
                if values[json_idx] is not None:
                    values[json_idx] = json_adapter(values[json_idx])
            values = tuple(values)
        rows.append(values)
    return rows


def _insert_batch(
    pg_conn, table: str, batch: pd.DataFrame, execute_values, json_adapter
) -> None:
    columns = list(batch.columns)
    quoted_columns = ", ".join(f'"{col}"' for col in columns)
    conflict = "ON CONFLICT DO NOTHING"
    if table == "preprocessed" and {"id", "content_type"}.issubset(columns):
        updates = ", ".join(
            f'"{column}" = EXCLUDED."{column}"' for column in columns if column not in {"id", "content_type"}
        )
        conflict = f'ON CONFLICT (id, content_type) DO UPDATE SET {updates}' if updates else conflict
    sql = f'INSERT INTO "{table}" ({quoted_columns}) VALUES %s {conflict}'
    rows = _row_values(table, batch, json_adapter)
    with pg_conn.cursor() as cursor:
        execute_values(cursor, sql, rows, page_size=min(len(rows), INSERT_PAGE_SIZE))


def _insert_batch_resilient(
    pg_conn,
    table: str,
    batch: pd.DataFrame,
    execute_values,
    json_adapter,
    reconnect,
    operational_error,
    *,
    single_row_attempt: int = 0,
) -> Any:
    """Insert a batch, reconnecting and reducing it if Neon closes the connection."""
    try:
        _insert_batch(pg_conn, table, batch, execute_values, json_adapter)
        return pg_conn
    except operational_error as exc:
        try:
            pg_conn.close()
        except Exception:
            pass

        if len(batch) > 1:
            reduced_size = max(1, len(batch) // 2)
            print(
                f"{table}: Neon closed the connection while inserting {len(batch)} rows; "
                f"retrying in batches of {reduced_size}"
            )
            current_conn = reconnect()
            for smaller_batch in _iter_batches(batch, reduced_size):
                current_conn = _insert_batch_resilient(
                    current_conn,
                    table,
                    smaller_batch,
                    execute_values,
                    json_adapter,
                    reconnect,
                    operational_error,
                )
                # Each recovered sub-batch must be durable before the next one;
                # another dropped connection rolls back its active transaction.
                current_conn.commit()
            return current_conn

        if single_row_attempt + 1 >= MAX_SINGLE_ROW_RETRIES:
            raise RuntimeError(
                f"Neon closed the connection repeatedly while inserting one row into "
                f"{table}. The row may be too large or the database may be unavailable."
            ) from exc

        time.sleep(2**single_row_attempt)
        return _insert_batch_resilient(
            reconnect(),
            table,
            batch,
            execute_values,
            json_adapter,
            reconnect,
            operational_error,
            single_row_attempt=single_row_attempt + 1,
        )


def _target_count(pg_conn, table: str) -> int:
    with pg_conn.cursor() as cursor:
        cursor.execute(f'SELECT COUNT(*) FROM "{table}"')
        return int(cursor.fetchone()[0])


def _typed_source_frame(conn, table: str, frame: pd.DataFrame) -> pd.DataFrame:
    if table not in {"sentiment_predictions", "topic_assignments", "embedding_2d"}:
        return frame
    if "content_type" in frame and frame["content_type"].notna().all():
        return frame
    key = "post_id" if table == "embedding_2d" else "id"
    if _table_exists(conn, "preprocessed"):
        known = pd.read_sql_query("SELECT id, content_type FROM preprocessed", conn)
        kinds = known.drop_duplicates().drop_duplicates("id", keep=False)
        inferred = frame[key].map(kinds.set_index("id")["content_type"])
        if "content_type" in frame:
            frame["content_type"] = frame["content_type"].fillna(inferred)
        else:
            frame["content_type"] = inferred
    elif "content_type" not in frame:
        frame["content_type"] = None
    return frame[frame["content_type"].notna()]


def run(args: argparse.Namespace) -> int:
    # Support both direct script execution and import by the pipeline/tests.
    try:
        from scripts.mirror_derived import DERIVED_TABLES, publish_snapshot
    except ModuleNotFoundError:
        from mirror_derived import DERIVED_TABLES, publish_snapshot
    source = Path(args.source)
    if not source.exists():
        print(f"Source SQLite database not found: {source}", file=sys.stderr)
        return 1
    if args.batch_size < 1:
        print("--batch-size must be at least 1.", file=sys.stderr)
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
                "Tables excluded from v1 because they are auxiliary or archival: "
                + ", ".join(present_excluded)
            )

        if args.dry_run:
            print("Dry run complete; no Neon writes performed.")
            return 0

        database_url = args.database_url or os.environ.get("DATABASE_URL")
        if not database_url:
            print(
                "DATABASE_URL or --database-url is required for live migration.",
                file=sys.stderr,
            )
            return 1

        psycopg2, Json, execute_values = _load_psycopg2()
        pg_conn = psycopg2.connect(database_url)
        try:
            from src.ml.record_identity import migrate_record_identity

            migrate_record_identity(pg_conn)
            if args.create_schema:
                schema_sql = Path(args.schema).read_text()
                seed_sql = Path(args.seed).read_text()
                with pg_conn.cursor() as cursor:
                    cursor.execute(schema_sql)
                    cursor.execute(seed_sql)
                pg_conn.commit()
                print(f"Schema applied from {args.schema}")
                print(f"Subreddit categories seeded from {args.seed}")

            derived_frames = {}
            # Hold a consistent source read snapshot across related tables.
            sqlite_conn.execute("BEGIN")
            for table in MIGRATION_ORDER:
                if not _table_exists(sqlite_conn, table):
                    print(f"{table}: missing in source, skipped")
                    continue
                df = pd.read_sql_query(f'SELECT * FROM "{table}"', sqlite_conn)
                df = _transform(table, _typed_source_frame(sqlite_conn, table, df))
                if table in DERIVED_TABLES:
                    derived_frames[table] = df
                    continue
                for batch in _iter_batches(df, args.batch_size):
                    if not batch.empty:
                        pg_conn = _insert_batch_resilient(
                            pg_conn,
                            table,
                            batch,
                            execute_values,
                            Json,
                            reconnect=lambda: psycopg2.connect(database_url),
                            operational_error=psycopg2.OperationalError,
                        )
                        # Commit each source batch so a later reconnect cannot lose
                        # successful work from earlier batches in the same table.
                        pg_conn.commit()
                print(
                    f"{table}: source={len(df)} target={_target_count(pg_conn, table)}"
                )
            if "sentiment_predictions" in derived_frames:
                with pg_conn.cursor() as cursor:
                    cursor.execute("""CREATE TABLE IF NOT EXISTS sentiment_model_active (
                        slot INTEGER PRIMARY KEY, model_dir TEXT NOT NULL, model_version TEXT NOT NULL
                    )""")
                pg_conn.commit()
                derived_frames.setdefault("sentiment_model_active", pd.DataFrame())
            else:
                derived_frames.pop("sentiment_model_active", None)
            if derived_frames:
                pg_conn = publish_snapshot(
                    pg_conn, derived_frames,
                    lambda conn, table, batch: _insert_batch(
                        conn, table, batch, execute_values, Json
                    ),
                    lambda: psycopg2.connect(database_url),
                    psycopg2.OperationalError, args.batch_size,
                )
                print("Derived data snapshot published atomically")
        finally:
            pg_conn.close()
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate SQLite Reddit data to Neon")
    parser.add_argument("--source", default="historical_reddit_data.db")
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--schema", default=str(SCHEMA_PATH))
    parser.add_argument("--seed", default=str(SEED_PATH))
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--create-schema", action="store_true", default=False)
    parser.add_argument("--dry-run", action="store_true", default=False)
    raise SystemExit(run(parser.parse_args()))


if __name__ == "__main__":
    main()
