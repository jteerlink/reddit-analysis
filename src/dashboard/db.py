"""Streamlit dashboard data access backed by the FastAPI DB query layer."""

import os
from datetime import date, timedelta
from typing import List, Optional, Tuple

import pandas as pd
import streamlit as st

from src.api import db as api_db

DB_PATH = os.environ.get("REDDIT_DB_PATH", "historical_reddit_data.db")


def _frame(records, columns: list[str] | None = None) -> pd.DataFrame:
    df = pd.DataFrame(records)
    if columns is not None and df.empty:
        return pd.DataFrame(columns=columns)
    return df


@st.cache_data(ttl=300)
def get_collection_summary() -> pd.DataFrame:
    return pd.DataFrame([api_db.get_collection_summary()])


@st.cache_data(ttl=300)
def get_last_ml_timestamp() -> Optional[str]:
    return api_db.get_collection_summary().get("last_ml_timestamp")


@st.cache_data(ttl=300)
def get_sentiment_summary() -> pd.DataFrame:
    return _frame(
        api_db.get_sentiment_summary(),
        ["label", "count", "mean_confidence"],
    )


@st.cache_data(ttl=300)
def get_trending_topics(n: int = 3) -> pd.DataFrame:
    return _frame(
        api_db.get_trending_topics(n),
        ["topic_id", "keywords", "doc_count", "week_start"],
    )


@st.cache_data(ttl=300)
def get_daily_volume(subreddits: tuple = (), days: int = 30) -> pd.DataFrame:
    return _frame(
        api_db.get_daily_volume(tuple(subreddits), days),
        ["date", "subreddit", "count"],
    )


@st.cache_data(ttl=300)
def get_sentiment_daily(subreddits: tuple = (), days: int = 90) -> pd.DataFrame:
    return _frame(
        api_db.get_sentiment_daily(tuple(subreddits), days),
        ["subreddit", "date", "mean_score", "rolling_7d", "rolling_30d"],
    )


@st.cache_data(ttl=300)
def get_change_points(subreddits: tuple = ()) -> pd.DataFrame:
    return _frame(
        api_db.get_change_points(tuple(subreddits)),
        ["subreddit", "date", "magnitude"],
    )


@st.cache_data(ttl=300)
def get_forecast(subreddits: tuple = ()) -> pd.DataFrame:
    return _frame(
        api_db.get_forecast(tuple(subreddits)),
        ["subreddit", "date", "yhat", "yhat_lower", "yhat_upper"],
    )


@st.cache_data(ttl=300)
def get_topics() -> pd.DataFrame:
    return _frame(
        api_db.get_topics(),
        ["topic_id", "keywords", "doc_count", "coherence_score"],
    )


@st.cache_data(ttl=300)
def get_emerging_topics(days: int = 7) -> pd.DataFrame:
    return _frame(
        api_db.get_emerging_topics(days),
        ["topic_id", "keywords", "doc_count"],
    )


@st.cache_data(ttl=300)
def get_topic_over_time(topic_id: int) -> pd.DataFrame:
    return _frame(
        api_db.get_topic_over_time(topic_id),
        ["week_start", "doc_count", "avg_sentiment"],
    )


@st.cache_data(ttl=300)
def get_topic_heatmap(n: int = 30) -> pd.DataFrame:
    df = _frame(
        api_db.get_topic_heatmap(n),
        ["topic_id", "week_start", "avg_sentiment"],
    )
    if df.empty:
        return df
    return df.pivot(index="topic_id", columns="week_start", values="avg_sentiment")


@st.cache_data(ttl=300)
def get_deep_dive(
    keyword: str = "",
    subreddits: tuple = (),
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    label_filter: str = "all",
    content_type_filter: str = "both",
) -> pd.DataFrame:
    return _frame(
        api_db.get_deep_dive(
            keyword=keyword,
            subreddits=tuple(subreddits),
            start_date=start_date,
            end_date=end_date,
            label_filter=label_filter,
            content_type_filter=content_type_filter,
            limit=500,
            offset=0,
        ),
        ["date", "subreddit", "content_type", "clean_text", "label", "confidence"],
    )


@st.cache_data(ttl=300)
def get_vader_agreement() -> pd.DataFrame:
    return _frame(
        api_db.get_vader_agreement(),
        ["subreddit", "agreement_rate", "total"],
    )


@st.cache_data(ttl=300)
def get_known_subreddits() -> List[str]:
    return api_db.get_known_subreddits()


@st.cache_data(ttl=300)
def get_date_range() -> Tuple[date, date]:
    result = api_db.get_date_range()
    try:
        return date.fromisoformat(result["start"]), date.fromisoformat(result["end"])
    except Exception:
        today = date.today()
        return today - timedelta(days=30), today
