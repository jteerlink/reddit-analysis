"""Analysis intelligence endpoints — read-only queries plus LLM enrichment."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from src.api import db as dashboard_db
from src.analysis import models, queries
from src.analysis.db import ANALYSIS_SCHEMA_VERSION, artifact_checksum, complete_artifact, enqueue_artifact, list_artifacts, missing_analysis_tables
from src.analysis.enrichment import _select_model
from src.analysis.ollama import OllamaConfig, chat
from src.db.connection import connection

logger = logging.getLogger(__name__)
router = APIRouter()


class EnrichRequest(BaseModel):
    kind: str  # "thread" | "events" | "brief" | "topics"
    post_id: Optional[str] = None


@router.get("/activity", response_model=List[models.ActivityEvent])
def activity(limit: int = Query(default=20, ge=1, le=100)):
    with connection(readonly=True) as conn:
        return queries.activity(conn, limit)


@router.get("/freshness", response_model=models.FreshnessResponse)
def freshness():
    with connection(readonly=True) as conn:
        data = queries.freshness(conn)
    configured = bool(OllamaConfig.from_env().api_key)
    data["llm_enrichment_available"] = configured
    data["llm_reason"] = None if configured else "missing_api_key"
    return data


@router.get("/model-registry", response_model=models.ModelRegistryResponse)
def model_registry():
    config = OllamaConfig.from_env()
    with connection(readonly=True) as conn:
        rows = queries.model_registry(conn)
    return {
        "default_host": config.host,
        "cloud_configured": bool(config.api_key),
        "local_override": not config.is_cloud,
        "models": rows,
        "error": None if rows else ("missing_api_key" if config.is_cloud and not config.api_key else None),
    }


@router.get("/artifacts", response_model=models.ArtifactStatusResponse)
def artifacts(kind: Optional[str] = Query(default=None), limit: int = Query(default=100, ge=1, le=500)):
    with connection(readonly=True) as conn:
        return {"artifacts": queries.artifacts(conn, kind=kind, limit=limit)}


def _provenance(state: str, label: str, source_table: str, source_ids: list[str], **extra) -> dict:
    return {
        "state": state,
        "label": label,
        "source": source_table,
        "source_table": source_table,
        "source_ids": source_ids,
        "schema_version": ANALYSIS_SCHEMA_VERSION,
        **{key: value for key, value in extra.items() if value is not None},
    }


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _summary_prompt(sentiment_rows: list[dict], volume_rows: list[dict]) -> list[dict]:
    recent_sentiment = sentiment_rows[-36:]
    recent_volume = volume_rows[-36:]
    return [
        {
            "role": "system",
            "content": (
                "You write concise chart notes for a Reddit analytics dashboard. "
                "Use only the supplied daily sentiment and volume data. "
                "Return plain text only, no markdown, in two short sentences or fewer."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Daily sentiment rows: {json.dumps(recent_sentiment, default=str)}\n"
                f"Daily volume rows: {json.dumps(recent_volume, default=str)}\n"
                "Summarize the visible trend and the strongest caveat."
            ),
        },
    ]


def _fallback_chart_summary(sentiment_rows: list[dict], volume_rows: list[dict]) -> str:
    if not sentiment_rows:
        return "No sentiment rows are available for the active dashboard window."
    ordered = sorted(sentiment_rows, key=lambda row: row.get("date") or "")
    first = ordered[0].get("mean_score")
    last = ordered[-1].get("mean_score")
    delta = None if first is None or last is None else float(last) - float(first)
    peak_volume = max((int(row.get("count") or 0) for row in volume_rows), default=0)
    if delta is None:
        return f"Sentiment data is available, but the active window has incomplete scores. Peak daily volume is {peak_volume:,} items."
    direction = "up" if delta > 0.05 else "down" if delta < -0.05 else "mostly flat"
    return f"Sentiment is {direction} across the active window. Peak daily volume is {peak_volume:,} items, so interpret thin-volume days cautiously."


@router.get("/narrative-events", response_model=models.NarrativeEventsResponse)
def narrative_events(limit: int = Query(default=50, ge=1, le=200)):
    with connection(readonly=True) as conn:
        missing = missing_analysis_tables(conn, ["narrative_events"])
        try:
            rows = [] if missing else queries.narrative_events(conn, limit)
            query_error = None
            llm_summaries = {
                json.loads(a.get("payload") or "{}").get("event_id"): a
                for a in list_artifacts(conn, kind="narrative_event_summary")
                if a.get("status") == "succeeded"
            }
        except queries.AnalysisQueryError as exc:
            rows = []
            query_error = str(exc)
            llm_summaries = {}
    # Merge LLM-generated titles/summaries where available
    for row in rows:
        artifact = llm_summaries.get(row.get("event_id"))
        if artifact:
            payload = json.loads(artifact.get("payload") or "{}")
            if payload.get("llm_label"):
                row["title"] = payload["llm_label"]
            if payload.get("llm_summary"):
                row["summary"] = payload["llm_summary"]
            if row.get("provenance"):
                row["provenance"]["label"] = "llm_artifact"
    state = "missing_schema" if missing else ("error" if query_error else ("ready" if rows else "unpopulated"))
    return {
        "items": rows,
        "state": state,
        "provenance": _provenance(
            state,
            "real_data" if state == "ready" else "missing_config",
            "narrative_events",
            [str(row["event_id"]) for row in rows[:25]],
            algorithm="change_point_ranker",
            detail=f"Missing tables: {', '.join(missing)}" if missing else query_error,
        ),
    }


@router.get("/overview-chart-summary", response_model=models.ChartSummaryResponse)
def overview_chart_summary(
    subreddits: List[str] = Query(default=[]),
    parents: List[str] = Query(default=[]),
    start: Optional[str] = Query(default=None),
    end: Optional[str] = Query(default=None),
):
    sentiment_rows = dashboard_db.get_sentiment_daily(tuple(subreddits), 90, start, end, tuple(parents))
    volume_rows = dashboard_db.get_daily_volume(tuple(subreddits), 90, start, end, tuple(parents))
    source_hash = artifact_checksum(
        {
            "kind": "overview_chart_summary",
            "subreddits": sorted(subreddits),
            "parents": sorted(parents),
            "start": start,
            "end": end,
            "sentiment": sentiment_rows[-36:],
            "volume": volume_rows[-36:],
        }
    )
    with connection(readonly=False) as conn:
        cached = next(
            (
                artifact
                for artifact in list_artifacts(conn, kind="overview_chart_summary", limit=50)
                if artifact.get("status") == "succeeded" and artifact.get("source_input_hash") == source_hash
            ),
            None,
        )
        if cached:
            payload = json.loads(cached.get("payload") or "{}")
            return {
                "summary": payload.get("summary") or _fallback_chart_summary(sentiment_rows, volume_rows),
                "state": "ready",
                "generated_at": payload.get("generated_at") or cached.get("freshness_timestamp"),
                "model_name": cached.get("model_name"),
                "source_input_hash": source_hash,
                "provenance": _provenance(
                    "ready",
                    "llm_artifact",
                    "analysis_artifacts",
                    [cached.get("artifact_id")],
                    artifact_id=cached.get("artifact_id"),
                    source_input_hash=source_hash,
                    provider=cached.get("provider"),
                ),
            }

        config = OllamaConfig.from_env()
        model = _select_model(conn, config)
        if not model:
            summary = _fallback_chart_summary(sentiment_rows, volume_rows)
            return {
                "summary": summary,
                "state": "missing_config",
                "generated_at": _now_iso(),
                "model_name": None,
                "source_input_hash": source_hash,
                "provenance": _provenance(
                    "missing_config",
                    "deterministic_fallback",
                    "sentiment_daily",
                    [],
                    source_input_hash=source_hash,
                    detail="Ollama model unavailable; returned deterministic summary.",
                ),
            }

        artifact = enqueue_artifact(
            conn,
            kind="overview_chart_summary",
            source_input_hash=source_hash,
            payload={"filters": {"subreddits": subreddits, "parents": parents, "start": start, "end": end}},
            provider="ollama",
            model_name=model,
            prompt_version="overview-chart-summary-v1",
        )
        try:
            content = chat(config, model, _summary_prompt(sentiment_rows, volume_rows), temperature=0.2, timeout=12)
            summary = " ".join(content.split())[:420] or _fallback_chart_summary(sentiment_rows, volume_rows)
        except Exception as exc:
            logger.warning("overview_chart_summary_llm_failed: %s", exc)
            summary = _fallback_chart_summary(sentiment_rows, volume_rows)
            return {
                "summary": summary,
                "state": "error",
                "generated_at": _now_iso(),
                "model_name": model,
                "source_input_hash": source_hash,
                "provenance": _provenance(
                    "error",
                    "deterministic_fallback",
                    "sentiment_daily",
                    [],
                    source_input_hash=source_hash,
                    provider="ollama",
                    detail=f"LLM summary failed: {exc.__class__.__name__}",
                ),
            }
        generated_at = _now_iso()
        complete_artifact(conn, artifact["artifact_id"], {"summary": summary, "generated_at": generated_at})
        return {
            "summary": summary,
            "state": "ready",
            "generated_at": generated_at,
            "model_name": model,
            "source_input_hash": source_hash,
            "provenance": _provenance(
                "ready",
                "llm_artifact",
                "analysis_artifacts",
                [artifact["artifact_id"]],
                artifact_id=artifact["artifact_id"],
                source_input_hash=source_hash,
                provider="ollama",
            ),
        }


@router.get("/embedding-map", response_model=models.EmbeddingMapResponse)
def embedding_map(limit: int = Query(default=5000, ge=1, le=5000)):
    with connection(readonly=True) as conn:
        missing = missing_analysis_tables(
            conn,
            ["embedding_2d", "topic_assignments", "topics", "preprocessed", "sentiment_predictions", "posts", "comments"],
        )
        try:
            rows = [] if missing else queries.embedding_map(conn, limit)
            query_error = None
        except queries.AnalysisQueryError as exc:
            rows = []
            query_error = str(exc)
    state = "missing_schema" if missing else ("error" if query_error else ("ready" if rows else "unpopulated"))
    topic_counts: dict[int, dict] = {}
    for row in rows:
        topic_id = row.get("topic_id") if row.get("topic_id") is not None else row.get("cluster_id")
        if topic_id is None:
            continue
        topic_id = int(topic_id)
        bucket = topic_counts.setdefault(topic_id, {"topic_id": topic_id, "label": row.get("topic_label"), "count": 0})
        bucket["count"] += 1
        if not bucket.get("label") and row.get("topic_label"):
            bucket["label"] = row.get("topic_label")
    total_points = len(rows)
    topics = sorted(topic_counts.values(), key=lambda item: item["count"], reverse=True)
    for topic in topics:
        topic["share"] = round(topic["count"] / total_points, 4) if total_points else 0.0
    largest = topics[0] if topics else None
    outlier_count = int(topic_counts.get(-1, {}).get("count", 0))
    largest_share = float(largest.get("share", 0.0)) if largest else 0.0
    collapsed = largest_share >= 0.85 and total_points >= 20
    return {
        "items": rows,
        "diagnostics": {
            "total_points": total_points,
            "topic_count": len([topic for topic in topics if topic["topic_id"] != -1]),
            "outlier_count": outlier_count,
            "outlier_share": round(outlier_count / total_points, 4) if total_points else 0.0,
            "largest_topic_id": largest.get("topic_id") if largest else None,
            "largest_topic_label": largest.get("label") if largest else None,
            "largest_topic_share": largest_share,
            "collapsed": collapsed,
            "warning": (
                f"{round(largest_share * 100)}% of visible points are assigned to one topic; review BERTopic settings or input diversity."
                if collapsed else None
            ),
            "topics": topics[:12],
        },
        "state": state,
        "provenance": _provenance(
            state,
            "real_data" if state == "ready" else "missing_config",
            "embedding_2d",
            [row["id"] for row in rows[:25]],
            algorithm="minilm_svd_projection",
            detail=f"Missing tables: {', '.join(missing)}" if missing else query_error,
        ),
    }


@router.get("/semantic-search", response_model=models.SemanticSearchResponse)
def semantic_search(q: str = Query(default="", max_length=200), limit: int = Query(default=50, ge=1, le=200)):
    with connection(readonly=True) as conn:
        missing = missing_analysis_tables(conn, ["preprocessed", "sentiment_predictions", "posts", "comments"])
        rows = [] if missing else queries.semantic_search(conn, q, limit)
    vector_ready = queries.semantic_vector_backend_ready()
    row_states = {str(row.get("state") or "ready") for row in rows}
    if missing:
        state = "missing_schema"
    elif "error" in row_states:
        state = "error"
    elif rows and row_states <= {"ready"}:
        state = "ready"
    elif rows and row_states:
        state = "missing_config"
    elif q.strip() and not vector_ready:
        state = "missing_config"
    else:
        state = "unpopulated"
    algorithm = rows[0].get("provenance", {}).get("algorithm") if rows else None
    return {
        "items": rows,
        "state": state,
        "provenance": _provenance(
            state,
            "real_data" if state == "ready" else "missing_config",
            "preprocessed",
            [row["id"] for row in rows[:25]],
            algorithm=algorithm or ("minilm_cosine" if state == "ready" else "lexical_overlap_fallback"),
            detail=f"Missing tables: {', '.join(missing)}" if missing else (None if state == "ready" else "Semantic vectors or query embedding model were unavailable; lexical fallback results are degraded."),
        ),
    }


@router.get("/thread-analysis/{post_id}", response_model=models.ThreadAnalysis)
def thread_analysis(post_id: str):
    with connection(readonly=True) as conn:
        result = queries.thread_analysis(conn, post_id)
        # Merge LLM positions_summary if a succeeded thread_analysis artifact exists
        llm_artifacts = [
            a for a in list_artifacts(conn, kind="thread_analysis")
            if a.get("status") == "succeeded"
            and json.loads(a.get("payload") or "{}").get("post_id") == post_id
        ]
    if llm_artifacts:
        payload = json.loads(llm_artifacts[0].get("payload") or "{}")
        result["positions_summary"] = payload.get("positions_summary", result.get("positions_summary"))
        if result.get("provenance"):
            result["provenance"]["label"] = "llm_artifact"
            result["provenance"]["provider"] = llm_artifacts[0].get("provider")
    return result


@router.get("/briefs/latest", response_model=models.AnalystBrief)
def latest_brief():
    with connection(readonly=True) as conn:
        brief = queries.latest_brief(conn)
    return brief or {
        "brief_id": "none",
        "period": "latest",
        "headline": "No analyst brief has been generated yet.",
        "sections": [],
        "source_events": [],
        "state": "unpopulated",
        "provenance": _provenance(
            "unpopulated",
            "missing_config",
            "analysis_artifacts",
            [],
            detail="No analyst_brief artifact is available.",
        ),
    }


@router.get("/briefs", response_model=models.AnalystBriefsResponse)
def briefs(limit: int = Query(default=10, ge=1, le=50)):
    with connection(readonly=True) as conn:
        rows = queries.briefs(conn, limit)
    state = "ready" if rows else "unpopulated"
    return {
        "items": rows,
        "state": state,
        "provenance": _provenance(
            state,
            "real_data" if rows else "missing_config",
            "analysis_artifacts",
            [str(row["brief_id"]) for row in rows[:25]],
            detail=None if rows else "No analyst brief artifact is available.",
        ),
    }


@router.post("/enrich")
def enrich(req: EnrichRequest):
    """Trigger on-demand LLM enrichment for a specific kind."""
    config = OllamaConfig.from_env()
    if config.is_cloud and not config.api_key:
        raise HTTPException(status_code=422, detail="missing_api_key: set OLLAMA_API_KEY to enable LLM enrichment")

    from src.analysis.enrichment import (
        _select_model,
        enrich_analyst_brief,
        enrich_narrative_events,
        enrich_thread_analysis,
        enrich_topic_labels,
    )

    with connection() as conn:
        model = _select_model(conn, config)
        if not model:
            raise HTTPException(status_code=503, detail="No Ollama model available")

        kind = req.kind
        if kind == "thread":
            if not req.post_id:
                raise HTTPException(status_code=400, detail="post_id required for thread enrichment")
            result = enrich_thread_analysis(conn, req.post_id, config, model)
            return {"kind": kind, "result": result}
        if kind == "events":
            count = enrich_narrative_events(conn, config, model)
            return {"kind": kind, "enriched": count}
        if kind == "brief":
            result = enrich_analyst_brief(conn, config, model)
            return {"kind": kind, "result": result}
        if kind == "topics":
            count = enrich_topic_labels(conn, config, model)
            return {"kind": kind, "enriched": count}
        raise HTTPException(status_code=400, detail=f"Unknown kind: {kind}. Use thread|events|brief|topics")
