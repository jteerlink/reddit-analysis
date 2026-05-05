"""Dashboard endpoints — one per db query function."""

from typing import List, Optional

from fastapi import APIRouter, Query

from src.api import db

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
):
    if subreddits or start or end:
        return db.get_sentiment_summary(tuple(subreddits), start, end)
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


@router.get("/topics/heatmap")
def topic_heatmap(n: int = Query(default=30, ge=1, le=100)):
    return db.get_topic_heatmap(n)


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


@router.get("/subreddits")
def subreddits():
    return db.get_known_subreddits()


@router.get("/date-range")
def date_range():
    return db.get_date_range()
