"""Read-only query helpers for analysis APIs."""

from __future__ import annotations

import json
import logging
import math
import re
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
from src.db.connection import execute, paramstyle

logger = logging.getLogger(__name__)


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
    source_table: Optional[str] = None, source_ids: Optional[list[str]] = None,
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
            severity = "success" if status == "succeeded" else ("error" if status == "failed" else "info")
            state = "stale_artifact" if status == "stale" else "ready"
            events.append(
                {
                    "timestamp": row["updated_at"] or "",
                    "type": row["kind"],
                    "severity": severity,
                    "title": f"{row['kind'].replace('_', ' ').title()} {status}",
                    "detail": row["error_message"] or f"Artifact {row['artifact_id'][:8]} is {status}",
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
                "provenance": _provenance("error", "missing_config", "analysis_artifacts", detail=str(exc)),
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
        count_row = execute(conn, f"SELECT COUNT(*) AS count FROM {table_name}").fetchone()
        count = int((_row_dict(count_row).get("count") if hasattr(count_row, "keys") else count_row[0]) or 0)
        if count == 0:
            return None
        timestamp = ""
        if timestamp_column:
            latest = execute(conn, f"SELECT MAX({timestamp_column}) AS latest FROM {table_name}").fetchone()
            timestamp = (_row_dict(latest).get("latest") if hasattr(latest, "keys") else latest[0]) or ""
        return {
            "timestamp": str(timestamp),
            "type": event_type,
            "severity": "success",
            "title": title,
            "detail": detail_template.format(count=count),
            "source_ids": [table_name],
            "state": "ready",
            "provenance": _provenance("ready", "real_data", table_name, producer_job="operational_activity"),
        }
    except Exception as exc:
        logger.exception("analysis_operational_activity_failed", extra={"table": table_name})
        return {
            "timestamp": "",
            "type": event_type,
            "severity": "error",
            "title": f"{title} unavailable",
            "detail": str(exc),
            "source_ids": [table_name],
            "state": "error",
            "provenance": _provenance("error", "missing_config", table_name, detail=str(exc)),
        }


def _operational_activity(conn: Any) -> list[dict]:
    candidates = [
        ("posts", "collection", "Collection data indexed", "{count} posts are available.", "timestamp"),
        ("comments", "collection", "Comment data indexed", "{count} comments are available.", "timestamp"),
        ("sentiment_predictions", "ml_run", "Sentiment predictions available", "{count} model predictions are available.", "predicted_at"),
        ("sentiment_forecast", "forecast", "Sentiment forecast available", "{count} forecast rows are available.", "date"),
        ("change_points", "drift_readiness", "Change-point signals available", "{count} drift/readiness signals are available.", "date"),
        ("narrative_events", "narrative_event", "Narrative events available", "{count} persisted narrative events are available.", "peak_date"),
    ]
    events = [
        event
        for event in (
            _optional_table_event(conn, table, event_type, title, detail, timestamp)
            for table, event_type, title, detail, timestamp in candidates
        )
        if event is not None
    ]
    return sorted(events, key=lambda item: item.get("timestamp") or "", reverse=True)[:8]


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
            state = "peaking" if abs(delta or 0) >= 0.5 else ("accelerating" if (delta or 0) > 0 else "cooling")
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


def embedding_map(conn, limit: int = 1000) -> list[dict]:
    if missing_analysis_tables(conn, ["embedding_2d"]):
        return []
    try:
        has_categories = not missing_analysis_tables(conn, ["subreddit_categories"])
        category_join = "LEFT JOIN subreddit_categories sc ON sc.subreddit = src.subreddit" if has_categories else ""
        parent_col = "sc.parent_id," if has_categories else "NULL AS parent_id,"
        rows = execute(
            conn,
            f"""
            SELECT e.post_id, e.x, e.y, e.cluster_id, ta.topic_id,
                   src.subreddit, {parent_col} src.date, p.clean_text, sp.label
            FROM embedding_2d e
            LEFT JOIN topic_assignments ta ON e.post_id = ta.id
            LEFT JOIN preprocessed p ON e.post_id = p.id
            LEFT JOIN sentiment_predictions sp ON e.post_id = sp.id
            LEFT JOIN (
                SELECT id, subreddit, DATE(timestamp) AS date FROM posts
                UNION ALL
                SELECT id, subreddit, DATE(timestamp) AS date FROM comments
            ) src ON e.post_id = src.id
            {category_join}
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


def semantic_search(conn, query: str, limit: int = 50) -> list[dict]:
    if not query.strip():
        return []
    marker = paramstyle()
    query_tokens = _tokenize(query)
    try:
        rows = execute(
            conn,
            f"""
            SELECT p.id, p.content_type, p.clean_text, p.embedding_key, src.subreddit, src.date,
                   sp.label, sp.confidence
            FROM preprocessed p
            LEFT JOIN sentiment_predictions sp ON p.id = sp.id
            LEFT JOIN (
                SELECT id, subreddit, DATE(timestamp) AS date FROM posts
                UNION ALL
                SELECT id, subreddit, DATE(timestamp) AS date FROM comments
            ) src ON p.id = src.id
            WHERE p.clean_text IS NOT NULL
            LIMIT 10000
            """,
        ).fetchall()
        vector_results = _semantic_vector_results(rows, query, limit)
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
            _semantic_result(row, score, "missing_config", "lexical_overlap_fallback")
            for score, row in scored[:limit]
        ]
    except Exception:
        logger.exception("semantic_search_failed")
        try:
            rows = execute(
                conn,
                f"""
                SELECT p.id, p.content_type, p.clean_text, src.subreddit, src.date,
                       sp.label, sp.confidence
                FROM preprocessed p
                LEFT JOIN sentiment_predictions sp ON p.id = sp.id
                LEFT JOIN (
                    SELECT id, subreddit, DATE(timestamp) AS date FROM posts
                    UNION ALL
                    SELECT id, subreddit, DATE(timestamp) AS date FROM comments
                ) src ON p.id = src.id
                WHERE p.clean_text LIKE {marker}
                LIMIT {marker}
                """,
                (f"%{query}%", limit),
            ).fetchall()
            return [_semantic_result(row, 0.25, "error", "like_error_fallback") for row in rows]
        except Exception:
            logger.exception("semantic_search_error_fallback_failed")
            return []


def _semantic_vector_results(rows: list[Any], query: str, limit: int) -> Optional[list[dict]]:
    index_path = Path("models/embeddings_index.json")
    cache_path = Path("models/embeddings_cache.npy")
    if not semantic_vector_backend_ready():
        return None
    try:
        from sentence_transformers import SentenceTransformer

        index = json.loads(index_path.read_text())
        embeddings = np.load(cache_path, mmap_mode="r")
        query_vector = SentenceTransformer("all-MiniLM-L6-v2").encode([query], normalize_embeddings=True)[0]
        scored = []
        for row in rows:
            key = row["embedding_key"] or row["id"]
            position = index.get(key)
            if position is None:
                continue
            score = _cosine(np.asarray(query_vector), np.asarray(embeddings[int(position)]))
            scored.append((score, row))
        if not scored:
            return None
        scored.sort(key=lambda item: item[0], reverse=True)
        return [_semantic_result(row, max(0.0, score), "ready", "minilm_cosine") for score, row in scored[:limit]]
    except Exception:
        logger.exception("semantic_vector_search_unavailable")
        return None


def semantic_vector_backend_ready() -> bool:
    if not Path("models/embeddings_index.json").exists() or not Path("models/embeddings_cache.npy").exists():
        return False
    try:
        from sentence_transformers import SentenceTransformer  # noqa: F401
    except Exception as exc:
        logger.warning("semantic_vector_backend_unavailable: %s", exc)
        return False
    return True


def _semantic_result(row: Any, score: float, state: str, algorithm: str) -> dict:
    label = "real_data" if state == "ready" else "missing_config"
    return {
        "id": row["id"],
        "score": round(float(score), 4),
        "date": row["date"],
        "subreddit": row["subreddit"],
        "content_type": row["content_type"],
        "label": row["label"],
        "confidence": row["confidence"],
        "text_preview": (row["clean_text"] or "")[:240],
        "state": state,
        "provenance": _provenance(state, label, "preprocessed", [row["id"]], algorithm=algorithm),
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
                "provenance": _provenance("unpopulated", "deterministic_fallback", "posts", [post_id]),
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
        return {"post_id": post_id, "state": "error", "provenance": _provenance("error", "missing_config", "comments")}


def latest_brief(conn) -> Optional[dict]:
    try:
        for kind, label in (("analyst_brief_llm", "llm_artifact"), ("analyst_brief", "deterministic_fallback")):
            rows = [row for row in list_artifacts(conn, kind=kind, limit=25) if row.get("status") == "succeeded"]
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
        deterministic_rows = [row for row in rows if row.get("kind") != "analyst_brief_llm"]
        llm_rows.sort(key=lambda row: row.get("freshness_timestamp") or row.get("updated_at") or "", reverse=True)
        deterministic_rows.sort(
            key=lambda row: row.get("freshness_timestamp") or row.get("updated_at") or "",
            reverse=True,
        )
        rows = llm_rows + deterministic_rows
        return [
            _brief_from_artifact(
                row,
                "llm_artifact" if row.get("kind") == "analyst_brief_llm" else "deterministic_fallback",
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
