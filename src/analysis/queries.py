"""Read-only query helpers for analysis APIs."""

from __future__ import annotations

import json
import logging
import math
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

import numpy as np

from src.analysis.db import (
    ANALYSIS_SCHEMA_VERSION,
    analysis_state,
    get_freshness,
    get_model_registry,
    list_artifacts,
    missing_analysis_tables,
)
from src.db.connection import execute, is_postgres_connection, paramstyle
from src.reddit_api.models import DEFAULT_SUBREDDIT_CATEGORIES

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SEMANTIC_MODEL_NAME = "all-MiniLM-L6-v2"
SEMANTIC_MODEL_DIR_ENV = "REDDIT_ANALYZER_MODEL_DIR"


class AnalysisQueryError(RuntimeError):
    """Raised when an analysis query cannot distinguish error from empty data."""


def _loads(value: Any, fallback):
    if value is None:
        return fallback
    try:
        return json.loads(value) if isinstance(value, str) else value
    except json.JSONDecodeError:
        return fallback


def _row_dict(row: Any) -> dict:
    return dict(row) if hasattr(row, "keys") else {}


def _provenance(
    state: str = "ready",
    label: str = "real_data",
    source_table: Optional[str] = None,
    source_ids: Optional[list[str]] = None,
    **extra,
) -> dict:
    return {
        "state": state,
        "label": label,
        "source": source_table,
        "source_table": source_table,
        "source_ids": source_ids or [],
        "schema_version": ANALYSIS_SCHEMA_VERSION,
        **{key: value for key, value in extra.items() if value is not None},
    }


def _tokenize(text: str) -> set[str]:
    return {part for part in re.findall(r"[a-z0-9]{3,}", text.lower())}


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    if not denom or math.isnan(denom):
        return 0.0
    return float(np.dot(a, b) / denom)


def _semantic_model_dir() -> Path:
    configured = os.environ.get(SEMANTIC_MODEL_DIR_ENV)
    path = Path(configured) if configured else PROJECT_ROOT / "models"
    return path if path.is_absolute() else PROJECT_ROOT / path


def _semantic_artifact_paths() -> tuple[Path, Path]:
    model_dir = _semantic_model_dir()
    return model_dir / "embeddings_index.json", model_dir / "embeddings_cache.npy"


@lru_cache(maxsize=1)
def _semantic_embedding_model():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(SEMANTIC_MODEL_NAME)


@lru_cache(maxsize=1)
def _semantic_artifacts() -> tuple[dict[str, int], np.ndarray]:
    index_path, cache_path = _semantic_artifact_paths()
    return json.loads(index_path.read_text()), np.load(cache_path, mmap_mode="r")


def _reset_semantic_caches() -> None:
    _semantic_embedding_model.cache_clear()
    _semantic_artifacts.cache_clear()


def _sql_text(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _column_exists(conn: Any, table_name: str, column_name: str) -> bool:
    marker = paramstyle()
    if is_postgres_connection(conn):
        row = execute(
            conn,
            f"""
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = {marker}
              AND column_name = {marker}
            LIMIT 1
            """,
            (table_name, column_name),
        ).fetchone()
        return row is not None

    rows = execute(conn, f"PRAGMA table_info({table_name})").fetchall()
    return any(
        (row["name"] if hasattr(row, "keys") else row[1]) == column_name for row in rows
    )


def activity(conn, limit: int = 20) -> list[dict]:
    readiness = analysis_state(conn)
    if readiness["state"] == "missing_schema":
        return [
            {
                "timestamp": "",
                "type": "analysis_schema",
                "severity": "warn",
                "title": "Analysis schema is not installed",
                "detail": readiness["reason"],
                "source_ids": [],
                "state": "missing_schema",
                "provenance": _provenance(
                    "missing_schema",
                    "missing_config",
                    "analysis_artifacts",
                    detail=readiness["reason"],
                ),
            }
        ]
    try:
        rows = execute(
            conn,
            f"""
            SELECT artifact_id, kind, status, updated_at, error_category, error_message
            FROM analysis_artifacts
            ORDER BY updated_at DESC
            LIMIT {paramstyle()}
            """,
            (limit,),
        ).fetchall()
        events = []
        for row in _operational_activity(conn):
            events.append(row)
        if not rows and not events:
            return [
                {
                    "timestamp": "",
                    "type": "analysis_artifacts",
                    "severity": "info",
                    "title": "Analysis artifacts are not populated",
                    "detail": "Run the analysis backfill job to populate enrichment artifacts.",
                    "source_ids": [],
                    "state": "unpopulated",
                    "provenance": _provenance(
                        "unpopulated",
                        "deterministic_fallback",
                        "analysis_artifacts",
                        producer_job="run_analysis_backfill",
                    ),
                }
            ]
        for row in rows:
            status = row["status"]
            severity = (
                "success"
                if status == "succeeded"
                else ("error" if status == "failed" else "info")
            )
            state = "stale_artifact" if status == "stale" else "ready"
            events.append(
                {
                    "timestamp": row["updated_at"] or "",
                    "type": row["kind"],
                    "severity": severity,
                    "title": f"{row['kind'].replace('_', ' ').title()} {status}",
                    "detail": row["error_message"]
                    or f"Artifact {row['artifact_id'][:8]} is {status}",
                    "source_ids": [row["artifact_id"]],
                    "state": state,
                    "provenance": _provenance(
                        state,
                        "stale_artifact" if state == "stale_artifact" else "real_data",
                        "analysis_artifacts",
                        [row["artifact_id"]],
                        artifact_id=row["artifact_id"],
                        freshness_timestamp=row["updated_at"],
                    ),
                }
            )
        return events
    except Exception as exc:
        logger.exception("analysis_activity_failed")
        return [
            {
                "timestamp": "",
                "type": "analysis_error",
                "severity": "error",
                "title": "Analysis activity failed",
                "detail": str(exc),
                "source_ids": [],
                "state": "error",
                "provenance": _provenance(
                    "error", "missing_config", "analysis_artifacts", detail=str(exc)
                ),
            }
        ]


def _optional_table_event(
    conn: Any,
    table_name: str,
    event_type: str,
    title: str,
    detail_template: str,
    timestamp_column: Optional[str] = None,
) -> Optional[dict]:
    if missing_analysis_tables(conn, [table_name]):
        return None
    try:
        count_row = execute(
            conn, f"SELECT COUNT(*) AS count FROM {table_name}"
        ).fetchone()
        count = int(
            (
                _row_dict(count_row).get("count")
                if hasattr(count_row, "keys")
                else count_row[0]
            )
            or 0
        )
        if count == 0:
            return None
        timestamp = ""
        event_detail = detail_template.format(count=count)
        event_title = title
        provenance_extra = {}
        # Forecast dates are predicted horizon points, not event timestamps.
        # Use the persisted run time when available and mark legacy rows whose
        # generation time cannot be established.
        if table_name == "sentiment_forecast" and timestamp_column == "date":
            if _column_exists(conn, table_name, "generated_at"):
                timestamp_column = "generated_at"
            else:
                provenance_extra["run_state"] = "unknown"
                event_title = f"{title} (generation time unknown)"
                event_detail += " Generation time is unavailable for this legacy forecast."
        if timestamp_column:
            latest = execute(
                conn, f"SELECT MAX({timestamp_column}) AS latest FROM {table_name}"
            ).fetchone()
            timestamp = (
                _row_dict(latest).get("latest")
                if hasattr(latest, "keys")
                else latest[0]
            ) or ""
        return {
            "timestamp": str(timestamp),
            "type": event_type,
            "severity": "success",
            "title": event_title,
            "detail": event_detail,
            "source_ids": [table_name],
            "state": "ready",
            "provenance": _provenance(
                "ready", "real_data", table_name,
                producer_job="operational_activity", **provenance_extra
            ),
        }
    except Exception as exc:
        logger.exception(
            "analysis_operational_activity_failed", extra={"table": table_name}
        )
        return {
            "timestamp": "",
            "type": event_type,
            "severity": "error",
            "title": f"{title} unavailable",
            "detail": str(exc),
            "source_ids": [table_name],
            "state": "error",
            "provenance": _provenance(
                "error", "missing_config", table_name, detail=str(exc)
            ),
        }


def _operational_activity(conn: Any) -> list[dict]:
    candidates = [
        (
            "posts",
            "collection",
            "Collection data indexed",
            "{count} posts are available.",
            "timestamp",
        ),
        (
            "comments",
            "collection",
            "Comment data indexed",
            "{count} comments are available.",
            "timestamp",
        ),
        (
            "sentiment_predictions",
            "ml_run",
            "Sentiment predictions available",
            "{count} model predictions are available.",
            "predicted_at",
        ),
        (
            "sentiment_forecast",
            "forecast",
            "Sentiment forecast available",
            "{count} forecast rows are available.",
            "date",
        ),
        (
            "change_points",
            "drift_readiness",
            "Change-point signals available",
            "{count} drift/readiness signals are available.",
            "date",
        ),
        (
            "narrative_events",
            "narrative_event",
            "Narrative events available",
            "{count} persisted narrative events are available.",
            "peak_date",
        ),
    ]
    events = [
        event
        for event in (
            _optional_table_event(conn, table, event_type, title, detail, timestamp)
            for table, event_type, title, detail, timestamp in candidates
        )
        if event is not None
    ]
    return sorted(events, key=lambda item: item.get("timestamp") or "", reverse=True)[
        :8
    ]


def freshness(conn) -> dict:
    return get_freshness(conn)


def model_registry(conn) -> list[dict]:
    return get_model_registry(conn)


def artifacts(conn, kind: Optional[str] = None, limit: int = 100) -> list[dict]:
    return list_artifacts(conn, kind=kind, limit=limit)


def narrative_events(conn, limit: int = 50) -> list[dict]:
    if missing_analysis_tables(conn, ["narrative_events"]):
        return []
    try:
        rows = execute(
            conn,
            f"""
            SELECT event_id, start_date, end_date, peak_date, peak_anomaly_score,
                   sentiment_delta, dominant_subreddits, top_terms, top_post_ids, auto_label
            FROM narrative_events
            ORDER BY peak_date DESC, ABS(COALESCE(sentiment_delta, 0)) DESC
            LIMIT {paramstyle()}
            """,
            (limit,),
        ).fetchall()
        result = []
        for row in rows:
            delta = row["sentiment_delta"]
            state = (
                "peaking"
                if abs(delta or 0) >= 0.5
                else ("accelerating" if (delta or 0) > 0 else "cooling")
            )
            result.append(
                {
                    "event_id": row["event_id"],
                    "start_date": row["start_date"],
                    "end_date": row["end_date"],
                    "peak_date": row["peak_date"],
                    "title": row["auto_label"] or "Narrative event",
                    "summary": row["auto_label"] or "Persisted anomaly event.",
                    "sentiment_delta": row["sentiment_delta"],
                    "dominant_subreddits": _loads(row["dominant_subreddits"], []),
                    "top_terms": _loads(row["top_terms"], []),
                    "top_post_ids": _loads(row["top_post_ids"], []),
                    "lifecycle_state": state,
                    "state": "ready",
                    "provenance": _provenance(
                        "ready",
                        "deterministic_fallback",
                        "narrative_events",
                        [str(row["event_id"])],
                        producer_job="backfill_narrative_events",
                        algorithm="change_point_ranker",
                    ),
                }
            )
        return result
    except Exception as exc:
        logger.exception("narrative_events_failed")
        raise AnalysisQueryError(str(exc)) from exc


def embedding_map(conn, limit: int = 5000) -> list[dict]:
    if missing_analysis_tables(conn, ["embedding_2d"]):
        return []
    try:
        has_categories = not missing_analysis_tables(conn, ["subreddit_categories"])
        has_topics = not missing_analysis_tables(conn, ["topics"])
        topic_join = (
            "LEFT JOIN topics t ON ta.topic_id = t.topic_id" if has_topics else ""
        )
        topic_keywords_expr = "t.keywords" if has_topics else "NULL"
        topic_label_expr = (
            "t.llm_label"
            if has_topics and _column_exists(conn, "topics", "llm_label")
            else "NULL"
        )
        post_parent_col = (
            "subreddit_parent_id"
            if _column_exists(conn, "posts", "subreddit_parent_id")
            else "NULL AS subreddit_parent_id"
        )
        comment_parent_col = (
            "subreddit_parent_id"
            if _column_exists(conn, "comments", "subreddit_parent_id")
            else "NULL AS subreddit_parent_id"
        )
        if has_categories:
            category_cte = ""
            category_join = (
                "LEFT JOIN subreddit_categories sc ON sc.subreddit = src.subreddit"
            )
        else:
            default_category_rows = ", ".join(
                f"({_sql_text(subreddit)}, {_sql_text(parent_id)})"
                for subreddit, parent_id, _display_name, _sort_order in DEFAULT_SUBREDDIT_CATEGORIES
            )
            category_cte = f"default_categories(subreddit, parent_id) AS (VALUES {default_category_rows}),"
            category_join = (
                "LEFT JOIN default_categories sc ON sc.subreddit = src.subreddit"
            )
        rows = execute(
            conn,
            f"""
            WITH src AS (
                SELECT id, subreddit, {post_parent_col}, DATE(timestamp) AS date FROM posts
                UNION ALL
                SELECT id, subreddit, {comment_parent_col}, DATE(timestamp) AS date FROM comments
            ),
            {category_cte}
            base AS (
                SELECT e.post_id, e.x, e.y, e.cluster_id, ta.topic_id,
                       COALESCE(NULLIF({topic_label_expr}, ''), NULLIF({topic_keywords_expr}, '')) AS topic_label,
                       CASE
                           WHEN {topic_label_expr} IS NOT NULL AND {topic_label_expr} != '' THEN 'llm_artifact'
                           WHEN {topic_keywords_expr} IS NOT NULL AND {topic_keywords_expr} != '' THEN 'deterministic_fallback'
                           ELSE 'unlabeled'
                       END AS label_source,
                       src.subreddit,
                       COALESCE(NULLIF(src.subreddit_parent_id, ''), sc.parent_id, 'OTHER') AS parent_id,
                       COALESCE(NULLIF(src.subreddit_parent_id, ''), sc.parent_id, 'OTHER') AS parent_group,
                       COALESCE(src.subreddit, 'unknown') AS subreddit_group,
                       src.date, p.clean_text, sp.label
                FROM embedding_2d e
                LEFT JOIN topic_assignments ta ON e.post_id = ta.id
                {topic_join}
                LEFT JOIN preprocessed p ON e.post_id = p.id
                LEFT JOIN sentiment_predictions sp ON e.post_id = sp.id
                LEFT JOIN src ON e.post_id = src.id
                {category_join}
            ),
            subreddit_ranked AS (
                SELECT *,
                       ROW_NUMBER() OVER (
                           PARTITION BY parent_group, subreddit_group
                           ORDER BY COALESCE(date, '') DESC, post_id
                       ) AS subreddit_rank
                FROM base
            ),
            parent_ranked AS (
                SELECT *,
                       ROW_NUMBER() OVER (
                           PARTITION BY parent_group
                           ORDER BY subreddit_rank, subreddit_group, COALESCE(date, '') DESC, post_id
                       ) AS parent_rank
                FROM subreddit_ranked
            )
            SELECT post_id, x, y, cluster_id, topic_id, topic_label, label_source, subreddit, parent_id, date, clean_text, label
            FROM parent_ranked
            ORDER BY parent_rank, parent_group, subreddit_rank, subreddit_group, COALESCE(date, '') DESC, post_id
            LIMIT {paramstyle()}
            """,
            (limit,),
        ).fetchall()
        return [
            {
                "id": row["post_id"],
                "x": float(row["x"]),
                "y": float(row["y"]),
                "cluster_id": int(row["cluster_id"]),
                "topic_id": row["topic_id"],
                "topic_label": row["topic_label"],
                "label_source": row["label_source"],
                "subreddit": row["subreddit"],
                "parent_id": row["parent_id"],
                "sentiment": row["label"],
                "date": row["date"],
                "preview": (row["clean_text"] or "")[:160],
                "state": "ready",
                "provenance": _provenance(
                    "ready",
                    "deterministic_fallback",
                    "embedding_2d",
                    [row["post_id"]],
                    producer_job="backfill_embedding_2d",
                    algorithm="minilm_svd_projection",
                ),
            }
            for row in rows
        ]
    except Exception as exc:
        logger.exception("embedding_map_failed")
        raise AnalysisQueryError(str(exc)) from exc


def _semantic_parent_subreddits(conn: Any, parents: tuple[str, ...]) -> tuple[str, ...]:
    """Resolve parent groups without requiring the optional category table."""
    if not parents:
        return ()
    values = {
        subreddit
        for subreddit, parent_id, _display_name, _sort_order in DEFAULT_SUBREDDIT_CATEGORIES
        if parent_id in parents
    }
    try:
        if _column_exists(conn, "subreddit_categories", "parent_id"):
            marker = paramstyle()
            rows = execute(
                conn,
                f"SELECT subreddit FROM subreddit_categories WHERE parent_id IN ({','.join([marker] * len(parents))})",
                list(parents),
            ).fetchall()
            values.update(row["subreddit"] if hasattr(row, "keys") else row[0] for row in rows)
    except Exception:
        # A missing optional table should not make search unavailable.
        logger.debug("semantic_parent_resolution_unavailable", exc_info=True)
    return tuple(sorted(value for value in values if value))


def _semantic_source_sql(conn: Any) -> str:
    """Return a source CTE with stable metadata across legacy schemas."""
    post_title = "title" if _column_exists(conn, "posts", "title") else "NULL"
    post_content = "content" if _column_exists(conn, "posts", "content") else "NULL"
    post_url = "url" if _column_exists(conn, "posts", "url") else "NULL"
    comment_content = "content" if _column_exists(conn, "comments", "content") else (
        "body" if _column_exists(conn, "comments", "body") else "NULL"
    )
    comment_post_id = "post_id" if _column_exists(conn, "comments", "post_id") else "NULL"
    comment_url = (
        "('https://www.reddit.com/comments/' || REPLACE(post_id, 't3_', '') || '/_/' || REPLACE(id, 't1_', '') || '/')"
        if comment_post_id != "NULL"
        else "NULL"
    )
    post_parent = "subreddit_parent_id" if _column_exists(conn, "posts", "subreddit_parent_id") else "NULL"
    comment_parent = "subreddit_parent_id" if _column_exists(conn, "comments", "subreddit_parent_id") else "NULL"
    return f"""
        SELECT id, subreddit, timestamp, DATE(timestamp) AS date,
               'post' AS content_type, {post_title} AS title,
               {post_content} AS original_text, {post_url} AS source_url,
               {post_parent} AS parent_id
        FROM posts
        UNION ALL
        SELECT id, subreddit, timestamp, DATE(timestamp) AS date,
               'comment' AS content_type, NULL AS title,
               {comment_content} AS original_text, {comment_url} AS source_url,
               {comment_parent} AS parent_id
        FROM comments
    """


def semantic_search(
    conn,
    query: str,
    limit: int = 50,
    subreddits: tuple[str, ...] = (),
    parents: tuple[str, ...] = (),
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    content_type: str = "both",
) -> list[dict]:
    if not query.strip():
        return []
    marker = paramstyle()
    query_tokens = _tokenize(query)
    try:
        conditions = ["p.clean_text IS NOT NULL"]
        params: list[Any] = []
        effective_subreddits = list(subreddits)
        for subreddit in _semantic_parent_subreddits(conn, parents):
            if subreddit not in effective_subreddits:
                effective_subreddits.append(subreddit)
        if effective_subreddits:
            conditions.append(f"src.subreddit IN ({','.join([marker] * len(effective_subreddits))})")
            params.extend(effective_subreddits)
        if start_date:
            conditions.append(f"src.timestamp >= {marker}")
            params.append(start_date)
        if end_date:
            # End dates are inclusive in the public filter contract.
            conditions.append(f"src.timestamp < {marker}")
            from datetime import datetime, timedelta

            params.append((datetime.strptime(end_date, "%Y-%m-%d").date() + timedelta(days=1)).isoformat())
        if content_type != "both":
            conditions.append(f"p.content_type = {marker}")
            params.append(content_type)
        rows = execute(
            conn,
            f"""
            WITH src AS ({_semantic_source_sql(conn)})
            SELECT p.id, p.content_type, p.clean_text, p.embedding_key,
                   src.subreddit, src.date, src.timestamp, src.title,
                   src.original_text, src.source_url, src.parent_id,
                   sp.label, sp.confidence
            FROM preprocessed p
            LEFT JOIN sentiment_predictions sp ON p.id = sp.id
            JOIN src ON p.id = src.id AND p.content_type = src.content_type
            WHERE {' AND '.join(conditions)}
            """,
            params,
        ).fetchall()
        vector_results, fallback_state, fallback_algorithm = _semantic_vector_results(
            rows, query, limit
        )
        if vector_results is not None:
            return vector_results

        scored = []
        for row in rows:
            text = row["clean_text"] or ""
            tokens = _tokenize(text)
            if not query_tokens or not tokens:
                continue
            overlap = len(query_tokens & tokens)
            if overlap == 0 and query.lower() not in text.lower():
                continue
            score = overlap / max(len(query_tokens | tokens), 1)
            if query.lower() in text.lower():
                score = max(score, 0.25)
            scored.append((score, row))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [
            _semantic_result(row, score, fallback_state, fallback_algorithm)
            for score, row in scored[:limit]
        ]
    except Exception:
        logger.exception("semantic_search_failed")
        try:
            rows = execute(
                conn,
                f"""
                SELECT p.id, p.content_type, p.clean_text, src.subreddit, src.date,
                       src.timestamp, src.title, src.original_text, src.source_url,
                       src.parent_id, sp.label, sp.confidence
                FROM preprocessed p
                LEFT JOIN sentiment_predictions sp ON p.id = sp.id
                JOIN ({_semantic_source_sql(conn)}) src ON p.id = src.id AND p.content_type = src.content_type
                WHERE p.clean_text LIKE {marker}
                LIMIT {marker}
                """,
                (f"%{query}%", limit),
            ).fetchall()
            return [
                _semantic_result(row, 0.25, "error", "like_error_fallback")
                for row in rows
            ]
        except Exception:
            logger.exception("semantic_search_error_fallback_failed")
            return []


def _semantic_vector_results(
    rows: list[Any], query: str, limit: int
) -> tuple[Optional[list[dict]], str, str]:
    index_path, cache_path = _semantic_artifact_paths()
    if not index_path.exists() or not cache_path.exists():
        logger.info("semantic_vector_missing_artifacts: %s %s", index_path, cache_path)
        return None, "missing_config", "missing_artifact_lexical_fallback"
    try:
        index, embeddings = _semantic_artifacts()
    except Exception:
        logger.exception("semantic_vector_artifact_load_failed")
        return None, "error", "artifact_load_error_lexical_fallback"

    try:
        model = _semantic_embedding_model()
    except ImportError as exc:
        logger.warning("semantic_vector_dependency_unavailable: %s", exc)
        return None, "missing_config", "dependency_unavailable_lexical_fallback"
    except Exception:
        logger.exception("semantic_vector_model_load_failed")
        return None, "error", "model_load_error_lexical_fallback"

    try:
        query_vector = np.asarray(model.encode([query], normalize_embeddings=True)[0], dtype=np.float32)
        query_norm = float(np.linalg.norm(query_vector))
        if not query_norm or math.isnan(query_norm):
            return None, "missing_config", "zero_query_vector_lexical_fallback"

        # Build one eligible position array and score it with matrix operations.
        # Chunking keeps peak memory bounded for large embedding caches.
        eligible: list[tuple[int, Any]] = []
        for row in rows:
            key = row["embedding_key"] or row["id"]
            # Older preprocessing runs stored numeric cache keys while newer
            # runs use Reddit IDs. Prefer the recorded key, then the source ID.
            position = index.get(key)
            if position is None:
                position = index.get(row["id"])
            if position is not None:
                try:
                    eligible.append((int(position), row))
                except (TypeError, ValueError):
                    continue
        if not eligible:
            return None, "missing_config", "no_vector_matches_lexical_fallback"

        positions = np.asarray([position for position, _row in eligible], dtype=np.intp)
        scored_values: list[float] = []
        scored_rows: list[Any] = []
        chunk_size = 8192
        for start in range(0, len(positions), chunk_size):
            matrix = np.asarray(embeddings[positions[start : start + chunk_size]], dtype=np.float32)
            norms = np.linalg.norm(matrix, axis=1)
            valid = np.isfinite(norms) & (norms > 0)
            if not np.any(valid):
                continue
            values = (matrix[valid] @ query_vector) / (norms[valid] * query_norm)
            chunk_rows = [row for _position, row in eligible[start : start + chunk_size]]
            for row_index, value in zip(np.flatnonzero(valid), values):
                if np.isfinite(value):
                    scored_values.append(float(value))
                    scored_rows.append(chunk_rows[int(row_index)])

        if not scored_values:
            return None, "missing_config", "zero_vector_matches_lexical_fallback"
        scored = list(zip(scored_values, scored_rows))
        # Stable ID tie-breaking makes pagination and repeated searches deterministic.
        scored.sort(key=lambda item: (-item[0], str(item[1]["id"])))
        return (
            [
                _semantic_result(row, max(0.0, score), "ready", "minilm_cosine")
                for score, row in scored[:limit]
            ],
            "ready",
            "minilm_cosine",
        )
    except Exception:
        logger.exception("semantic_vector_search_unavailable")
        return None, "error", "vector_error_lexical_fallback"


def semantic_vector_backend_ready() -> bool:
    index_path, cache_path = _semantic_artifact_paths()
    if not index_path.exists() or not cache_path.exists():
        return False
    try:
        from sentence_transformers import SentenceTransformer  # noqa: F401
    except Exception as exc:
        logger.warning("semantic_vector_backend_unavailable: %s", exc)
        return False
    return True


def _semantic_result(row: Any, score: float, state: str, algorithm: str) -> dict:
    label = "real_data" if state == "ready" else "missing_config"
    clean_text = row["clean_text"] or ""
    return {
        "id": row["id"],
        "score": round(float(score), 4),
        "date": row["date"],
        "timestamp": row["timestamp"] if "timestamp" in row.keys() else None,
        "subreddit": row["subreddit"],
        "content_type": row["content_type"],
        "title": row["title"] if "title" in row.keys() else None,
        "original_text": row["original_text"] if "original_text" in row.keys() else None,
        "clean_text": clean_text,
        "source_url": row["source_url"] if "source_url" in row.keys() else None,
        "label": row["label"],
        "confidence": row["confidence"],
        "text_preview": clean_text[:240],
        "state": state,
        "provenance": _provenance(
            state, label, "preprocessed", [row["id"]], algorithm=algorithm
        ),
    }


def thread_analysis(conn, post_id: str) -> dict:
    marker = paramstyle()
    try:
        post = execute(
            conn,
            f"SELECT id, title, subreddit, num_comments FROM posts WHERE id = {marker}",
            (post_id,),
        ).fetchone()
        if not post:
            return {
                "post_id": post_id,
                "state": "unpopulated",
                "provenance": _provenance(
                    "unpopulated", "deterministic_fallback", "posts", [post_id]
                ),
            }
        rows = execute(
            conn,
            f"""
            SELECT c.id, c.body, sp.label, sp.confidence
            FROM comments c
            JOIN sentiment_predictions sp ON c.id = sp.id
            WHERE c.post_id = {marker}
            ORDER BY sp.confidence ASC, c.score DESC
            LIMIT 200
            """,
            (post_id,),
        ).fetchall()
        labels = [row["label"] for row in rows]
        pos = labels.count("positive")
        neg = labels.count("negative")
        neutral = labels.count("neutral")
        total = max(len(labels), 1)
        spread = abs(pos - neg) / total
        controversy = min(pos, neg) / total
        representatives = [
            {
                "id": row["id"],
                "label": row["label"],
                "confidence": row["confidence"],
                "preview": (row["body"] or "")[:180],
            }
            for row in rows[:5]
        ]
        return {
            "post_id": post_id,
            "title": post["title"],
            "subreddit": post["subreddit"],
            "comment_count": int(post["num_comments"] or len(labels) or 0),
            "sentiment_spread": spread,
            "controversy_score": controversy,
            "positions_summary": "Persisted deterministic summary; LLM enrichment has not been generated for this thread.",
            "positive_count": pos,
            "negative_count": neg,
            "neutral_count": neutral,
            "representative_comments": representatives,
            "state": "ready" if labels else "unpopulated",
            "provenance": _provenance(
                "ready" if labels else "unpopulated",
                "deterministic_fallback",
                "comments",
                [post_id],
                algorithm="sentiment_distribution",
            ),
        }
    except Exception:
        return {
            "post_id": post_id,
            "state": "error",
            "provenance": _provenance("error", "missing_config", "comments"),
        }


def latest_brief(conn) -> Optional[dict]:
    try:
        for kind, label in (
            ("analyst_brief_llm", "llm_artifact"),
            ("analyst_brief", "deterministic_fallback"),
        ):
            rows = [
                row
                for row in list_artifacts(conn, kind=kind, limit=25)
                if row.get("status") == "succeeded"
            ]
            if rows:
                return _brief_from_artifact(rows[0], label)
        return None
    except Exception:
        return None


def briefs(conn, limit: int = 10) -> list[dict]:
    try:
        rows = [
            row
            for kind in ("analyst_brief_llm", "analyst_brief")
            for row in list_artifacts(conn, kind=kind, limit=limit)
            if row.get("status") == "succeeded"
        ]
        llm_rows = [row for row in rows if row.get("kind") == "analyst_brief_llm"]
        deterministic_rows = [
            row for row in rows if row.get("kind") != "analyst_brief_llm"
        ]
        llm_rows.sort(
            key=lambda row: row.get("freshness_timestamp")
            or row.get("updated_at")
            or "",
            reverse=True,
        )
        deterministic_rows.sort(
            key=lambda row: row.get("freshness_timestamp")
            or row.get("updated_at")
            or "",
            reverse=True,
        )
        rows = llm_rows + deterministic_rows
        return [
            _brief_from_artifact(
                row,
                (
                    "llm_artifact"
                    if row.get("kind") == "analyst_brief_llm"
                    else "deterministic_fallback"
                ),
            )
            for row in rows[:limit]
        ]
    except Exception:
        logger.exception("analysis_briefs_failed")
        return []


def _brief_from_artifact(row: dict, label: str) -> dict:
    payload = _loads(row.get("payload"), {})
    return {
        "brief_id": payload.get("brief_id", row["artifact_id"]),
        "period": payload.get("period", "latest"),
        "headline": payload.get("headline", "Latest Reddit intelligence snapshot"),
        "sections": payload.get("sections", []),
        "source_events": payload.get("source_events", []),
        "generated_at": payload.get("generated_at") or row.get("freshness_timestamp"),
        "model_name": payload.get("model_name") or row.get("model_name"),
        "prompt_version": payload.get("prompt_version") or row.get("prompt_version"),
        "evidence_schema_version": payload.get("evidence_schema_version") or row.get("schema_version"),
        "evidence_status": payload.get("evidence_status") or (
            "legacy"
            if not (payload.get("evidence_schema_version") or row.get("schema_version"))
            else "unverified"
        ),
        "state": "ready",
        "provenance": _provenance(
            "ready",
            label,
            "analysis_artifacts",
            [row["artifact_id"]],
            artifact_id=row["artifact_id"],
            source_input_hash=row.get("source_input_hash"),
            freshness_timestamp=row.get("freshness_timestamp"),
            provider=row.get("provider"),
        ),
    }
