"""
Reddit Analyzer — ML Layer

Phase 2 machine learning pipeline: preprocessing, sentiment, topic modeling,
and time series analysis.
"""

from .preprocessing import EmbeddingGenerator, TextCleaner, run_preprocessing
from .db import (
    get_connection,
    ensure_preprocessed_table,
    iter_raw_records,
    upsert_preprocessed,
    ensure_sentiment_table,
    iter_unscored_records,
    upsert_sentiment,
    ensure_topics_tables,
    iter_preprocessed_for_topics,
    upsert_topics,
    upsert_topic_assignments,
    upsert_topic_over_time,
)
from .sentiment import LABEL2ID, ID2LABEL, predict_batch, run_batch_inference, train
from .topics import EmbeddingCache, TopicModeler, run_topic_modeling

__all__ = [
    # preprocessing
    "TextCleaner",
    "EmbeddingGenerator",
    "run_preprocessing",
    # db — preprocessed
    "get_connection",
    "ensure_preprocessed_table",
    "iter_raw_records",
    "upsert_preprocessed",
    # db — sentiment
    "ensure_sentiment_table",
    "iter_unscored_records",
    "upsert_sentiment",
    # db — topics
    "ensure_topics_tables",
    "iter_preprocessed_for_topics",
    "upsert_topics",
    "upsert_topic_assignments",
    "upsert_topic_over_time",
    # sentiment
    "LABEL2ID",
    "ID2LABEL",
    "train",
    "predict_batch",
    "run_batch_inference",
    # topics
    "EmbeddingCache",
    "TopicModeler",
    "run_topic_modeling",
]
