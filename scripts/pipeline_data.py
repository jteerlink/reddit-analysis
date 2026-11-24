"""Run the data-retention and Neon reconciliation phases of a pipeline."""

import argparse
import os
import sqlite3
import sys
from contextlib import closing
from datetime import datetime, timezone
from hashlib import md5
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.reddit_api.retention import prune_expired_records, retention_cutoff  # noqa: E402

COMPOSITE_KEYS = {
    "preprocessed": ("id", "content_type"),
    "sentiment_predictions": ("id", "content_type"),
    "topic_assignments": ("id", "content_type"),
    "embedding_2d": ("post_id", "content_type"),
    "collection_metadata": ("subreddit", "collection_timestamp"),
    "batch_collections": ("subreddit", "collection_timestamp"),
    "topic_over_time": ("topic_id", "week_start"),
    "sentiment_daily": ("subreddit", "date"),
    "sentiment_moving_avg": ("subreddit", "date"),
    "change_points": ("subreddit", "date"),
    "sentiment_forecast": ("subreddit", "date"),
    "topic_sentiment_trends": ("topic_id", "date"),
}
KEY_COLUMNS = {
    "sentiment_model_active": "slot", "topics": "topic_id", "analysis_schema_version": "key",
    "llm_model_registry": "model_name", "analysis_runs": "run_id", "analysis_artifacts": "artifact_id",
    "cluster_labels": "cluster_id", "narrative_events": "event_id",
}
HISTORY_TABLES = {"api_metrics", "collection_metadata", "batch_collections", "artifact_status_history"}
LOCK_SQL = "SELECT pg_advisory_xact_lock(hashtext('reddit-analyzer.pipeline-data'))"


def _target_schema(conn: Any) -> dict[str, dict[str, str]]:
    with conn.cursor() as cursor:
        cursor.execute("""
            SELECT table_name, column_name, data_type FROM information_schema.columns
            WHERE table_schema = current_schema()
        """)
        schema: dict[str, dict[str, str]] = {}
        for table, column, kind in cursor:
            schema.setdefault(table, {})[column] = kind
        return schema


def _changed_rows(conn: Any, table: str, frame: Any, schema: dict[str, str]) -> tuple[list[int], bool]:
    """Return locally managed rows missing or changed on Neon, plus target-only keys."""
    from scripts.migrate_to_neon import _quote_identifier

    keys = COMPOSITE_KEYS.get(table, (KEY_COLUMNS.get(table, "id"),))
    columns = list(keys)
    if table not in HISTORY_TABLES:
        columns.extend(column for column in frame.columns if column not in keys)
    hashed = {column for column in columns[len(keys):] if schema[column] in {"text", "character varying"}}
    projection = ", ".join(
        f"md5({_quote_identifier(column)})" if column in hashed else _quote_identifier(column)
        for column in columns
    )
    with conn.cursor() as cursor:
        cursor.execute(f"SELECT {projection} FROM {_quote_identifier(table)}")
        target = {row[:len(keys)]: row[len(keys):] for row in cursor}
    different = []
    for index, row in enumerate(frame[columns].itertuples(index=False, name=None)):
        key = row[:len(keys)]
        right = target.pop(key, None)
        left = tuple(
            md5(value.encode()).hexdigest() if column in hashed and value is not None else value
            for column, value in zip(columns[len(keys):], row[len(keys):])
        )
        if right is None or left != right:
            different.append(index)
    return different, bool(target)


def _reconcile(conn: Any, frames: dict[str, Any], cutoff: datetime | None, batch_size: int, create_schema: bool) -> list[str]:
    from scripts.migrate_to_neon import SCHEMA_PATH, SEED_PATH, _insert_batch, _iter_batches, _load_psycopg2
    from scripts.mirror_derived import DERIVED_TABLES, replace_snapshot
    from src.ml.record_identity import migrate_record_identity

    _, json_adapter, execute_values = _load_psycopg2()
    with conn.cursor() as cursor:
        cursor.execute("SET LOCAL lock_timeout = '15s'")
        cursor.execute("SET LOCAL statement_timeout = '90s'")
        cursor.execute(LOCK_SQL)
    migrate_record_identity(conn, commit=False)
    schema = _target_schema(conn)
    missing = [table for table, frame in frames.items() if set(frame.columns) - schema.get(table, {}).keys()]
    if missing and create_schema:
        with conn.cursor() as cursor:
            cursor.execute(SCHEMA_PATH.read_text())
            cursor.execute(SEED_PATH.read_text())
        schema = _target_schema(conn)
        missing = [table for table, frame in frames.items() if set(frame.columns) - schema.get(table, {}).keys()]
    if missing:
        raise ValueError("Neon schema is missing source columns in " + ", ".join(missing))

    removed = prune_expired_records(conn, cutoff) if cutoff else {}
    if sum(removed.values()):
        print("Neon retention removed " + ", ".join(f"{table}={count}" for table, count in removed.items() if count))

    derived = {}
    changed = []
    for table, frame in frames.items():
        rows, extra = _changed_rows(conn, table, frame, schema[table])
        if table in DERIVED_TABLES:
            if rows or extra:
                derived[table] = frame
                changed.append(table)
        elif rows:
            changed.append(table)
            keys = COMPOSITE_KEYS.get(table, (KEY_COLUMNS.get(table, "id"),))
            for batch in _iter_batches(frame.iloc[rows], batch_size):
                _insert_batch(conn, table, batch, execute_values, json_adapter,
                              update_on=() if table in HISTORY_TABLES else keys)

    if derived:
        replace_snapshot(conn, derived,
                         lambda db, table, batch: _insert_batch(db, table, batch, execute_values, json_adapter),
                         batch_size)
    for table in changed:
        rows, extra = _changed_rows(conn, table, frames[table], schema[table])
        if rows or (extra and table in DERIVED_TABLES):
            raise ValueError(f"Neon verification still differs for {table}")
    return list(dict.fromkeys(changed + [table for table, count in removed.items() if count]))


def sync_neon(source: Path, dsn: str, cutoff: datetime | None, batch_size: int, create_schema: bool) -> list[str]:
    import pandas as pd

    from scripts.migrate_to_neon import MIGRATION_ORDER, _load_psycopg2, _table_exists, _transform, _typed_source_frame

    if batch_size < 1:
        raise ValueError("NEON_MIRROR_BATCH_SIZE must be at least 1")
    psycopg2, _, _ = _load_psycopg2()
    with closing(sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True)) as local:
        local.execute("BEGIN")
        frames = {}
        for table in MIGRATION_ORDER:
            if _table_exists(local, table):
                frame = pd.read_sql_query(f'SELECT * FROM "{table}"', local)
                frames[table] = _transform(table, _typed_source_frame(local, table, frame))
        if "sentiment_predictions" in frames:
            frames.setdefault("sentiment_model_active", pd.DataFrame(columns=["slot", "model_dir", "model_version"]))
    for attempt in range(2):
        try:
            with closing(psycopg2.connect(dsn, connect_timeout=10)) as neon, neon:
                return _reconcile(neon, frames, cutoff, batch_size, create_schema)
        except psycopg2.OperationalError:
            if attempt:
                raise
            print("Neon connection interrupted. Retrying reconciliation.")
    raise AssertionError("Neon reconciliation retry state")


def prune(source: str, cutoff: datetime) -> dict[str, int]:
    from src.ml.db import get_connection

    postgres = bool(os.environ.get("DATABASE_URL")) or source.startswith(("postgres://", "postgresql://"))
    if postgres:
        with closing(get_connection(source)) as conn, conn:
            with conn.cursor() as cursor:
                cursor.execute("SET LOCAL lock_timeout = '15s'")
                cursor.execute(LOCK_SQL)
            return prune_expired_records(conn, cutoff)
    with closing(sqlite3.connect(Path(source).resolve().as_uri() + "?mode=rw", uri=True, timeout=15)) as conn, conn:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("BEGIN IMMEDIATE")
        return prune_expired_records(conn, cutoff)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("cutoff", "prune", "sync"))
    parser.add_argument("--db")
    parser.add_argument("--cutoff", type=datetime.fromisoformat)
    args = parser.parse_args()
    if args.action == "cutoff":
        print(retention_cutoff(datetime.now(timezone.utc)).isoformat())
        return 0
    if not args.db or (args.action == "prune" and args.cutoff is None):
        parser.error("--db is required, and prune also requires --cutoff")
    if args.cutoff and args.cutoff.tzinfo is None:
        parser.error("--cutoff must include a timezone")

    load_dotenv(PROJECT_ROOT / ".env")
    try:
        if args.action == "prune":
            removed = prune(args.db, args.cutoff)
            summary = ", ".join(f"{table}={count}" for table, count in removed.items() if count) or "no expired rows"
            print(f"Retention before {args.cutoff.isoformat()} completed ({summary}).")
            return 0
        if os.environ.get("DATABASE_URL") or args.db.startswith(("postgres://", "postgresql://")):
            print("Neon mirror skipped because the pipeline is already using PostgreSQL.")
            return 0
        dsn = os.environ.get("NEON_DATABASE_URL")
        if not dsn:
            print("Neon mirror skipped because NEON_DATABASE_URL is unset.")
            return 0
        print("Checking Neon against the SQLite snapshot.", flush=True)
        changed = sync_neon(Path(args.db), dsn, args.cutoff, int(os.getenv("NEON_MIRROR_BATCH_SIZE", "250")),
                            os.getenv("NEON_MIRROR_CREATE_SCHEMA", "true").lower() not in {"false", "0", "no"})
        summary = "reconciled " + ", ".join(changed) if changed else "already in sync"
        print(f"Neon verified at {datetime.now(timezone.utc).isoformat(timespec='seconds')} ({summary}).")
        return 0
    except (ValueError, sqlite3.Error) as exc:
        print(f"Pipeline {args.action} failed: {exc}", file=sys.stderr)
    except Exception as exc:
        state = getattr(exc, "pgcode", None)
        print(f"Pipeline {args.action} failed: {type(exc).__name__}" + (f" (SQLSTATE {state})" if state else ""),
              file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
