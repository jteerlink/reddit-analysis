"""Read-only analysis intelligence endpoints."""

from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Query

from src.analysis import models
from src.analysis.ollama import OllamaConfig
from src.analysis import queries
from src.analysis.db import ANALYSIS_SCHEMA_VERSION, missing_analysis_tables
from src.db.connection import connection

router = APIRouter()


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


@router.get("/narrative-events", response_model=models.NarrativeEventsResponse)
def narrative_events(limit: int = Query(default=50, ge=1, le=200)):
    with connection(readonly=True) as conn:
        rows = queries.narrative_events(conn, limit)
        missing = missing_analysis_tables(conn, ["narrative_events"])
    state = "missing_schema" if missing else ("ready" if rows else "unpopulated")
    return {
        "items": rows,
        "state": state,
        "provenance": _provenance(
            state,
            "real_data" if state == "ready" else "missing_config",
            "narrative_events",
            [str(row["event_id"]) for row in rows[:25]],
            algorithm="change_point_ranker",
            detail=f"Missing tables: {', '.join(missing)}" if missing else None,
        ),
    }


@router.get("/embedding-map", response_model=models.EmbeddingMapResponse)
def embedding_map(limit: int = Query(default=1000, ge=1, le=5000)):
    with connection(readonly=True) as conn:
        missing = missing_analysis_tables(
            conn,
            ["embedding_2d", "topic_assignments", "preprocessed", "sentiment_predictions", "posts", "comments"],
        )
        rows = [] if missing else queries.embedding_map(conn, limit)
    state = "missing_schema" if missing else ("ready" if rows else "unpopulated")
    return {
        "items": rows,
        "state": state,
        "provenance": _provenance(
            state,
            "real_data" if state == "ready" else "missing_config",
            "embedding_2d",
            [row["id"] for row in rows[:25]],
            algorithm="minilm_svd_projection",
            detail=f"Missing tables: {', '.join(missing)}" if missing else None,
        ),
    }


@router.get("/semantic-search", response_model=models.SemanticSearchResponse)
def semantic_search(q: str = Query(default="", max_length=200), limit: int = Query(default=50, ge=1, le=200)):
    with connection(readonly=True) as conn:
        missing = missing_analysis_tables(conn, ["preprocessed", "sentiment_predictions", "posts", "comments"])
        rows = [] if missing else queries.semantic_search(conn, q, limit)
    vector_ready = Path("models/embeddings_index.json").exists() and Path("models/embeddings_cache.npy").exists()
    state = "missing_schema" if missing else ("ready" if rows and all(row.get("state") == "ready" for row in rows) else ("missing_config" if q.strip() and not vector_ready else ("ready" if rows else "unpopulated")))
    return {
        "items": rows,
        "state": state,
        "provenance": _provenance(
            state,
            "real_data" if state == "ready" else "missing_config",
            "preprocessed",
            [row["id"] for row in rows[:25]],
            algorithm="minilm_cosine" if state == "ready" else "lexical_overlap_fallback",
            detail=f"Missing tables: {', '.join(missing)}" if missing else (None if state == "ready" else "Semantic vectors or query embedding model were unavailable; lexical fallback results are degraded."),
        ),
    }


@router.get("/thread-analysis/{post_id}", response_model=models.ThreadAnalysis)
def thread_analysis(post_id: str):
    with connection(readonly=True) as conn:
        return queries.thread_analysis(conn, post_id)


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
