"""Dashboard endpoints — one per db query function."""

from typing import List, Optional

from fastapi import APIRouter, Query

from src.api import db
from src.analysis import models
from src.analysis.db import ANALYSIS_SCHEMA_VERSION

router = APIRouter()


@router.get("/summary")
def summary(
    subreddits: List[str] = Query(default=[]),
    start: Optional[str] = Query(default=None),
    end: Optional[str] = Query(default=None),
):
    data = (
        db.get_collection_summary(tuple(subreddits), start, end)
        if subreddits or start or end
        else db.get_collection_summary()
    )
    data["trending_topics"] = db.get_trending_topics(n=3)
    return data


@router.get("/sentiment/summary")
def sentiment_summary(
    subreddits: List[str] = Query(default=[]),
    start: Optional[str] = Query(default=None),
    end: Optional[str] = Query(default=None),
    weighted: bool = Query(default=False),
):
    if subreddits or start or end:
        return db.get_sentiment_summary(tuple(subreddits), start, end, weighted)
    if weighted:
        return db.get_sentiment_summary(weighted=True)
    return db.get_sentiment_summary()


@router.get("/sentiment/daily")
def sentiment_daily(
    subreddits: List[str] = Query(default=[]),
    days: int = Query(default=90, ge=1, le=365),
    start: Optional[str] = Query(default=None),
    end: Optional[str] = Query(default=None),
):
    if start or end:
        return db.get_sentiment_daily(tuple(subreddits), days, start, end)
    return db.get_sentiment_daily(tuple(subreddits), days)


@router.get("/sentiment/change-points")
def change_points(subreddits: List[str] = Query(default=[])):
    return db.get_change_points(tuple(subreddits))


@router.get("/sentiment/forecast")
def forecast(subreddits: List[str] = Query(default=[])):
    return db.get_forecast(tuple(subreddits))


@router.get("/volume/daily")
def volume_daily(
    subreddits: List[str] = Query(default=[]),
    days: int = Query(default=30, ge=1, le=365),
    start: Optional[str] = Query(default=None),
    end: Optional[str] = Query(default=None),
):
    if start or end:
        return db.get_daily_volume(tuple(subreddits), days, start, end)
    return db.get_daily_volume(tuple(subreddits), days)


@router.get("/topics")
def topics():
    return db.get_topics()


@router.get("/topics/emerging")
def emerging_topics(days: int = Query(default=7, ge=1, le=90)):
    return db.get_emerging_topics(days)


def _response(items: list[dict], source_table: str, algorithm: str, readiness: dict | None = None) -> dict:
    readiness = readiness or {"state": "ready", "reason": None}
    state = readiness["state"] if readiness["state"] != "ready" else ("ready" if items else "unpopulated")
    return {
        "items": items,
        "state": state,
        "provenance": {
            "state": state,
            "label": "real_data" if state == "ready" else "missing_config",
            "source": source_table,
            "source_table": source_table,
            "source_ids": [],
            "schema_version": ANALYSIS_SCHEMA_VERSION,
            "algorithm": algorithm,
            "detail": readiness.get("reason"),
        },
    }


@router.get("/topics/heatmap", response_model=models.TopicHeatmapResponse)
def topic_heatmap(n: int = Query(default=30, ge=1, le=100)):
    readiness = db.get_table_state(("topic_over_time", "topics"))
    return _response([] if readiness["state"] != "ready" else db.get_topic_heatmap(n), "topic_over_time", "topic_week_sentiment", readiness)


@router.get("/topics/graph")
def topic_graph(
    n: int = Query(default=50, ge=1, le=100),
    min_similarity: float = Query(default=0.15, ge=0, le=1),
    subreddits: List[str] = Query(default=[]),
):
    return db.get_topic_graph(n=n, min_similarity=min_similarity, subreddits=tuple(subreddits))


@router.get("/topics/{topic_id}/over-time")
def topic_over_time(topic_id: int):
    return db.get_topic_over_time(topic_id)


@router.get("/posts/search")
def posts_search(
    keyword: str = Query(default=""),
    subreddits: List[str] = Query(default=[]),
    start: Optional[str] = Query(default=None),
    end: Optional[str] = Query(default=None),
    label: str = Query(default="all"),
    content_type: str = Query(default="both"),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    return db.get_deep_dive(
        keyword=keyword,
        subreddits=tuple(subreddits),
        start_date=start,
        end_date=end,
        label_filter=label,
        content_type_filter=content_type,
        limit=limit,
        offset=offset,
    )


@router.get("/model/vader-agreement")
def vader_agreement():
    return db.get_vader_agreement()


@router.get("/model/low-confidence", response_model=models.LowConfidenceResponse)
def low_confidence(limit: int = Query(default=50, ge=1, le=500)):
    readiness = db.get_table_state(("preprocessed", "sentiment_predictions", "posts", "comments"))
    return _response([] if readiness["state"] != "ready" else db.get_low_confidence_examples(limit), "sentiment_predictions", "confidence_rank", readiness)


@router.get("/model/vader-disagreements", response_model=models.VaderDisagreementResponse)
def vader_disagreements(limit: int = Query(default=50, ge=1, le=500)):
    readiness = db.get_table_state(("preprocessed", "sentiment_predictions", "posts", "comments"))
    return _response([] if readiness["state"] != "ready" else db.get_vader_disagreements(limit), "sentiment_predictions", "vader_label_compare", readiness)


@router.get("/model/confidence-by-subreddit", response_model=models.ConfidenceBySubredditResponse)
def confidence_by_subreddit():
    readiness = db.get_table_state(("preprocessed", "sentiment_predictions", "posts", "comments"))
    return _response([] if readiness["state"] != "ready" else db.get_confidence_by_subreddit(), "sentiment_predictions", "confidence_group_by_subreddit", readiness)


@router.get("/subreddits")
def subreddits():
    return db.get_known_subreddits()


@router.get("/date-range")
def date_range():
    return db.get_date_range()
