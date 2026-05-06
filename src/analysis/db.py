"""Persistence helpers for durable analysis artifacts."""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, Optional

from src.db.connection import execute, is_postgres_connection, paramstyle

logger = logging.getLogger(__name__)

ANALYSIS_SCHEMA_VERSION = 1
TERMINAL_STATUSES = {"succeeded", "failed", "canceled"}
REQUIRED_ANALYSIS_TABLES = {
    "analysis_schema_version",
    "llm_model_registry",
    "analysis_runs",
    "analysis_artifacts",
    "artifact_status_history",
    "embedding_2d",
    "cluster_labels",
    "narrative_events",
}


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _expired_iso(seconds: int) -> str:
    return (
        datetime.now(timezone.utc) + timedelta(seconds=seconds)
    ).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, default=str)


def _row_dict(row: Any) -> dict:
    return dict(row) if hasattr(row, "keys") else {}


def _table_exists(conn: Any, table_name: str) -> bool:
    marker = paramstyle()
    try:
        if is_postgres_connection(conn):
            row = execute(
                conn,
                f"""
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = {marker}
                LIMIT 1
                """,
                (table_name,),
            ).fetchone()
        else:
            row = execute(
                conn,
                f"SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = {marker}",
                (table_name,),
            ).fetchone()
        return row is not None
    except Exception:
        logger.exception("analysis_table_check_failed", extra={"table": table_name})
        return False


def missing_analysis_tables(conn: Any, required: Iterable[str] = REQUIRED_ANALYSIS_TABLES) -> list[str]:
    return sorted(table for table in required if not _table_exists(conn, table))


def _parse_iso(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def analysis_state(conn: Any, source_table: str = "analysis_artifacts", stale_after_days: int = 7) -> dict:
    missing = missing_analysis_tables(conn)
    if missing:
        return {
            "state": "missing_schema",
            "missing_tables": missing,
            "reason": f"Missing analysis tables: {', '.join(missing)}",
        }
    marker = paramstyle()
    try:
        row = execute(conn, f"SELECT COUNT(*) AS count FROM {source_table}").fetchone()
        count = int((_row_dict(row).get("count") if hasattr(row, "keys") else row[0]) or 0)
    except Exception as exc:
        logger.exception("analysis_state_failed", extra={"source_table": source_table})
        return {"state": "error", "missing_tables": [], "reason": str(exc)}
    if count == 0:
        return {"state": "unpopulated", "missing_tables": [], "reason": f"{source_table} has no rows"}
    stale = execute(
        conn,
        f"SELECT COUNT(*) AS count FROM analysis_artifacts WHERE status = {marker}",
        ("stale",),
    ).fetchone()
    stale_count = int((_row_dict(stale).get("count") if hasattr(stale, "keys") else stale[0]) or 0)
    if stale_count:
        return {"state": "stale_artifact", "missing_tables": [], "reason": f"{stale_count} stale artifacts"}
    latest_success = execute(
        conn,
        f"SELECT MAX(freshness_timestamp) AS latest FROM analysis_artifacts WHERE status = {marker}",
        ("succeeded",),
    ).fetchone()
    latest_value = _row_dict(latest_success).get("latest") if hasattr(latest_success, "keys") else latest_success[0]
    latest_dt = _parse_iso(latest_value)
    if latest_dt:
        now = datetime.now(timezone.utc)
        if latest_dt.tzinfo is None:
            latest_dt = latest_dt.replace(tzinfo=timezone.utc)
        if now - latest_dt > timedelta(days=stale_after_days):
            return {
                "state": "stale_artifact",
                "missing_tables": [],
                "reason": f"Latest successful artifact is older than {stale_after_days} days",
            }
    return {"state": "ready", "missing_tables": [], "reason": None}


def artifact_checksum(payload: Any) -> str:
    return hashlib.sha256(_json(payload).encode("utf-8")).hexdigest()


def idempotency_key(kind: str, source_input_hash: str, schema_version: int = 1) -> str:
    raw = f"{kind}:{source_input_hash}:{schema_version}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def ensure_analysis_tables(conn: Any) -> None:
    """Create additive analysis schema for SQLite or Neon/Postgres."""
    if is_postgres_connection(conn):
        json_type = "JSONB"
        bool_type = "BOOLEAN"
        real_type = "DOUBLE PRECISION"
        timestamp_type = "TIMESTAMPTZ"
        serial_type = "BIGSERIAL"
        default_now = "NOW()"
    else:
        json_type = "TEXT"
        bool_type = "INTEGER"
        real_type = "REAL"
        timestamp_type = "TEXT"
        serial_type = "INTEGER"
        default_now = "CURRENT_TIMESTAMP"

    execute(conn, f"""
        CREATE TABLE IF NOT EXISTS analysis_schema_version (
            key TEXT PRIMARY KEY,
            version INTEGER NOT NULL,
            applied_at {timestamp_type} DEFAULT {default_now}
        )
    """)
    execute(conn, f"""
        CREATE TABLE IF NOT EXISTS llm_model_registry (
            model_name TEXT PRIMARY KEY,
            provider TEXT NOT NULL DEFAULT 'ollama',
            available {bool_type} NOT NULL DEFAULT 0,
            metadata {json_type},
            discovered_at {timestamp_type} DEFAULT {default_now}
        )
    """)
    execute(conn, f"""
        CREATE TABLE IF NOT EXISTS analysis_runs (
            run_id TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'queued',
            provider TEXT,
            model_name TEXT,
            prompt_version TEXT,
            input_hash TEXT NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0,
            max_attempts INTEGER NOT NULL DEFAULT 3,
            lease_owner TEXT,
            lease_expires_at {timestamp_type},
            started_at {timestamp_type},
            finished_at {timestamp_type},
            error_category TEXT,
            error_message TEXT,
            resume_token TEXT,
            created_at {timestamp_type} DEFAULT {default_now},
            updated_at {timestamp_type} DEFAULT {default_now}
        )
    """)
    execute(conn, f"""
        CREATE TABLE IF NOT EXISTS analysis_artifacts (
            artifact_id TEXT PRIMARY KEY,
            run_id TEXT,
            kind TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'queued',
            idempotency_key TEXT NOT NULL UNIQUE,
            payload {json_type},
            payload_location TEXT,
            checksum TEXT,
            content_type TEXT NOT NULL DEFAULT 'application/json',
            schema_version INTEGER NOT NULL DEFAULT 1,
            provider TEXT,
            model_name TEXT,
            prompt_version TEXT,
            source_input_hash TEXT NOT NULL,
            freshness_timestamp {timestamp_type},
            attempts INTEGER NOT NULL DEFAULT 0,
            max_attempts INTEGER NOT NULL DEFAULT 3,
            lease_owner TEXT,
            lease_expires_at {timestamp_type},
            error_category TEXT,
            error_message TEXT,
            retry_after {timestamp_type},
            resume_token TEXT,
            parent_artifact_id TEXT,
            created_at {timestamp_type} DEFAULT {default_now},
            updated_at {timestamp_type} DEFAULT {default_now}
        )
    """)
    execute(conn, f"""
        CREATE TABLE IF NOT EXISTS artifact_status_history (
            id {serial_type} PRIMARY KEY,
            artifact_id TEXT NOT NULL,
            from_status TEXT,
            to_status TEXT NOT NULL,
            reason TEXT,
            worker_id TEXT,
            created_at {timestamp_type} DEFAULT {default_now}
        )
    """)
    execute(conn, f"""
        CREATE TABLE IF NOT EXISTS embedding_2d (
            post_id TEXT PRIMARY KEY,
            x {real_type} NOT NULL,
            y {real_type} NOT NULL,
            cluster_id INTEGER NOT NULL
        )
    """)
    execute(conn, """
        CREATE TABLE IF NOT EXISTS cluster_labels (
            cluster_id INTEGER PRIMARY KEY,
            label TEXT NOT NULL,
            keywords TEXT NOT NULL,
            doc_count INTEGER NOT NULL DEFAULT 0
        )
    """)
    execute(conn, f"""
        CREATE TABLE IF NOT EXISTS narrative_events (
            event_id {serial_type} PRIMARY KEY,
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL,
            peak_date TEXT NOT NULL,
            peak_anomaly_score {real_type},
            sentiment_delta {real_type},
            dominant_subreddits TEXT,
            top_terms TEXT,
            top_post_ids TEXT,
            auto_label TEXT,
            created_at {timestamp_type} DEFAULT {default_now}
        )
    """)
    execute(conn, "CREATE INDEX IF NOT EXISTS idx_analysis_artifacts_kind ON analysis_artifacts(kind)")
    execute(conn, "CREATE INDEX IF NOT EXISTS idx_analysis_artifacts_status ON analysis_artifacts(status)")
    execute(conn, "CREATE INDEX IF NOT EXISTS idx_analysis_artifacts_freshness ON analysis_artifacts(freshness_timestamp)")
    execute(conn, "CREATE INDEX IF NOT EXISTS idx_analysis_runs_status ON analysis_runs(status)")
    execute(conn, "CREATE INDEX IF NOT EXISTS idx_events_peak ON narrative_events(peak_date)")
    execute(conn, "CREATE INDEX IF NOT EXISTS idx_emb2d_cluster ON embedding_2d(cluster_id)")
    execute(
        conn,
        "INSERT OR REPLACE INTO analysis_schema_version (key, version, applied_at) VALUES (?, ?, ?)"
        if not is_postgres_connection(conn)
        else """
        INSERT INTO analysis_schema_version (key, version, applied_at)
        VALUES (%s, %s, %s)
        ON CONFLICT (key) DO UPDATE SET version = EXCLUDED.version, applied_at = EXCLUDED.applied_at
        """,
        ("analysis", ANALYSIS_SCHEMA_VERSION, _now()),
    )
    conn.commit()


def enqueue_artifact(
    conn: Any,
    kind: str,
    source_input_hash: str,
    payload: Optional[dict] = None,
    provider: Optional[str] = None,
    model_name: Optional[str] = None,
    prompt_version: Optional[str] = None,
    schema_version: int = 1,
    max_attempts: int = 3,
) -> dict:
    key = idempotency_key(kind, source_input_hash, schema_version)
    marker = paramstyle()
    existing = execute(
        conn,
        f"SELECT * FROM analysis_artifacts WHERE idempotency_key = {marker}",
        (key,),
    ).fetchone()
    if existing:
        return _row_dict(existing)

    artifact_id = str(uuid.uuid4())
    now = _now()
    payload_text = _json(payload or {})
    checksum = artifact_checksum(payload or {})
    execute(
        conn,
        f"""
        INSERT INTO analysis_artifacts (
            artifact_id, kind, status, idempotency_key, payload, checksum,
            schema_version, provider, model_name, prompt_version, source_input_hash,
            freshness_timestamp, max_attempts, created_at, updated_at
        ) VALUES ({",".join([marker] * 15)})
        """,
        (
            artifact_id,
            kind,
            "queued",
            key,
            payload_text,
            checksum,
            schema_version,
            provider,
            model_name,
            prompt_version,
            source_input_hash,
            now,
            max_attempts,
            now,
            now,
        ),
    )
    _record_history(conn, artifact_id, None, "queued", "enqueue", None)
    conn.commit()
    logger.info("analysis_artifact_enqueued", extra={"artifact_id": artifact_id, "kind": kind})
    return get_artifact(conn, artifact_id) or {}


def _record_history(
    conn: Any,
    artifact_id: str,
    from_status: Optional[str],
    to_status: str,
    reason: Optional[str],
    worker_id: Optional[str],
) -> None:
    marker = paramstyle()
    execute(
        conn,
        f"""
        INSERT INTO artifact_status_history
            (artifact_id, from_status, to_status, reason, worker_id)
        VALUES ({marker}, {marker}, {marker}, {marker}, {marker})
        """,
        (artifact_id, from_status, to_status, reason, worker_id),
    )


def get_artifact(conn: Any, artifact_id: str) -> Optional[dict]:
    marker = paramstyle()
    row = execute(conn, f"SELECT * FROM analysis_artifacts WHERE artifact_id = {marker}", (artifact_id,)).fetchone()
    return _row_dict(row) if row else None


def list_artifacts(conn: Any, kind: Optional[str] = None, limit: int = 100) -> list[dict]:
    marker = paramstyle()
    if not _table_exists(conn, "analysis_artifacts"):
        return []
    try:
        if kind:
            rows = execute(
                conn,
                f"SELECT * FROM analysis_artifacts WHERE kind = {marker} ORDER BY updated_at DESC LIMIT {marker}",
                (kind, limit),
            ).fetchall()
        else:
            rows = execute(
                conn,
                f"SELECT * FROM analysis_artifacts ORDER BY updated_at DESC LIMIT {marker}",
                (limit,),
            ).fetchall()
        return [_row_dict(row) for row in rows]
    except Exception:
        logger.exception("analysis_artifacts_read_failed")
        return []


def claim_next_artifact(
    conn: Any,
    worker_id: str,
    lease_seconds: int = 600,
    max_concurrency: int = 1,
) -> Optional[dict]:
    """Claim one queued/stale artifact. Designed for a single local worker by default."""
    marker = paramstyle()
    now = _now()
    lease_until = _expired_iso(lease_seconds)
    running = execute(
        conn,
        f"SELECT COUNT(*) FROM analysis_artifacts WHERE status = {marker} AND lease_owner = {marker}",
        ("running", worker_id),
    ).fetchone()[0]
    if int(running or 0) >= max_concurrency:
        return None

    if is_postgres_connection(conn):
        row = execute(
            conn,
            """
            SELECT *
            FROM analysis_artifacts
            WHERE status IN ('queued', 'stale')
               OR (status = 'running' AND lease_expires_at IS NOT NULL AND lease_expires_at < %s)
            ORDER BY created_at ASC
            LIMIT 1
            FOR UPDATE SKIP LOCKED
            """,
            (now,),
        ).fetchone()
    else:
        row = execute(
            conn,
            """
            SELECT *
            FROM analysis_artifacts
            WHERE status IN ('queued', 'stale')
               OR (status = 'running' AND lease_expires_at IS NOT NULL AND lease_expires_at < ?)
            ORDER BY created_at ASC
            LIMIT 1
            """,
            (now,),
        ).fetchone()
    if not row:
        return None

    row_dict = _row_dict(row)
    previous = row_dict["status"]
    artifact_id = row_dict["artifact_id"]
    updated = execute(
        conn,
        f"""
        UPDATE analysis_artifacts
        SET status = 'running',
            attempts = attempts + 1,
            lease_owner = {marker},
            lease_expires_at = {marker},
            updated_at = {marker},
            error_category = NULL,
            error_message = NULL
        WHERE artifact_id = {marker}
          AND (
              status IN ('queued', 'stale')
              OR (status = 'running' AND lease_expires_at IS NOT NULL AND lease_expires_at < {marker})
          )
        """,
        (worker_id, lease_until, now, artifact_id, now),
    )
    if getattr(updated, "rowcount", 0) != 1:
        conn.rollback()
        return None
    _record_history(conn, artifact_id, previous, "running", "claim", worker_id)
    conn.commit()
    logger.info("analysis_artifact_claimed", extra={"artifact_id": artifact_id, "worker_id": worker_id})
    return get_artifact(conn, artifact_id)


def complete_artifact(conn: Any, artifact_id: str, payload: dict) -> dict:
    marker = paramstyle()
    now = _now()
    payload_text = _json(payload)
    checksum = artifact_checksum(payload)
    row = get_artifact(conn, artifact_id)
    previous = row["status"] if row else None
    execute(
        conn,
        f"""
        UPDATE analysis_artifacts
        SET status = 'succeeded',
            payload = {marker},
            checksum = {marker},
            freshness_timestamp = {marker},
            lease_owner = NULL,
            lease_expires_at = NULL,
            updated_at = {marker}
        WHERE artifact_id = {marker}
        """,
        (payload_text, checksum, now, now, artifact_id),
    )
    _record_history(conn, artifact_id, previous, "succeeded", "complete", None)
    conn.commit()
    logger.info("analysis_artifact_succeeded", extra={"artifact_id": artifact_id})
    return get_artifact(conn, artifact_id) or {}


def fail_artifact(conn: Any, artifact_id: str, category: str, message: str, retry_after_seconds: int = 300) -> dict:
    marker = paramstyle()
    now = _now()
    row = get_artifact(conn, artifact_id)
    previous = row["status"] if row else None
    attempts = int(row.get("attempts") or 0) if row else 0
    max_attempts = int(row.get("max_attempts") or 3) if row else 3
    retryable = category in {"timeout", "provider_unavailable", "rate_limited"}
    status = "queued" if retryable and attempts < max_attempts else "failed"
    retry_after = _expired_iso(retry_after_seconds) if status == "queued" else None
    execute(
        conn,
        f"""
        UPDATE analysis_artifacts
        SET status = {marker},
            error_category = {marker},
            error_message = {marker},
            retry_after = {marker},
            lease_owner = NULL,
            lease_expires_at = NULL,
            updated_at = {marker}
        WHERE artifact_id = {marker}
        """,
        (status, category, message[:1000], retry_after, now, artifact_id),
    )
    _record_history(conn, artifact_id, previous, status, category, None)
    conn.commit()
    logger.warning("analysis_artifact_failed", extra={"artifact_id": artifact_id, "category": category, "status": status})
    return get_artifact(conn, artifact_id) or {}


def upsert_models(conn: Any, provider: str, models: Iterable[dict]) -> None:
    marker = paramstyle()
    now = _now()
    for model in models:
        name = str(model.get("name") or model.get("model") or "").strip()
        if not name:
            continue
        metadata = _json(model)
        if is_postgres_connection(conn):
            execute(
                conn,
                """
                INSERT INTO llm_model_registry (model_name, provider, available, metadata, discovered_at)
                VALUES (%s, %s, TRUE, %s, %s)
                ON CONFLICT (model_name) DO UPDATE SET
                    provider = EXCLUDED.provider,
                    available = EXCLUDED.available,
                    metadata = EXCLUDED.metadata,
                    discovered_at = EXCLUDED.discovered_at
                """,
                (name, provider, metadata, now),
            )
        else:
            execute(
                conn,
                f"""
                INSERT OR REPLACE INTO llm_model_registry
                    (model_name, provider, available, metadata, discovered_at)
                VALUES ({marker}, {marker}, {marker}, {marker}, {marker})
                """,
                (name, provider, 1, metadata, now),
            )
    conn.commit()


def get_model_registry(conn: Any) -> list[dict]:
    if not _table_exists(conn, "llm_model_registry"):
        return []
    try:
        rows = execute(
            conn,
            "SELECT model_name, provider, available, metadata, discovered_at FROM llm_model_registry ORDER BY model_name",
        ).fetchall()
        return [_row_dict(row) for row in rows]
    except Exception:
        return []


def get_freshness(conn: Any) -> dict:
    readiness = analysis_state(conn)
    if readiness["state"] == "missing_schema":
        return {
            "queued": 0,
            "running": 0,
            "failed": 0,
            "succeeded": 0,
            "latest_artifact_at": None,
            "latest_success_at": None,
            "enrichment_available": False,
            "state": "missing_schema",
            "missing_tables": readiness["missing_tables"],
            "reason": readiness["reason"],
            "provenance": {
                "state": "missing_schema",
                "label": "missing_config",
                "source": "analysis_artifacts",
                "source_table": "analysis_artifacts",
                "schema_version": ANALYSIS_SCHEMA_VERSION,
                "detail": readiness["reason"],
            },
        }
    try:
        rows = execute(
            conn,
            "SELECT status, COUNT(*) AS count, MAX(freshness_timestamp) AS latest FROM analysis_artifacts GROUP BY status",
        ).fetchall()
        counts = {"queued": 0, "running": 0, "failed": 0, "succeeded": 0}
        latest = None
        latest_success = None
        for row in rows:
            item = _row_dict(row)
            status = item.get("status")
            if status in counts:
                counts[status] = int(item.get("count") or 0)
            if item.get("latest") and (latest is None or str(item["latest"]) > str(latest)):
                latest = item["latest"]
            if status == "succeeded" and item.get("latest"):
                latest_success = item["latest"]
        return {
            **counts,
            "latest_artifact_at": latest,
            "latest_success_at": latest_success,
            "enrichment_available": bool(latest),
            "state": readiness["state"],
            "missing_tables": readiness["missing_tables"],
            "reason": readiness["reason"],
            "provenance": {
                "state": readiness["state"],
                "label": "stale_artifact" if readiness["state"] == "stale_artifact" else "real_data",
                "source": "analysis_artifacts",
                "source_table": "analysis_artifacts",
                "schema_version": ANALYSIS_SCHEMA_VERSION,
                "freshness_timestamp": latest,
                "detail": readiness["reason"],
            },
        }
    except Exception:
        return {
            "queued": 0,
            "running": 0,
            "failed": 0,
            "succeeded": 0,
            "latest_artifact_at": None,
            "latest_success_at": None,
            "enrichment_available": False,
            "state": "error",
            "missing_tables": [],
            "reason": "Failed to read analysis freshness",
        }
