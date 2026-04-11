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
)
from .sentiment import LABEL2ID, ID2LABEL, predict_batch, run_batch_inference, train

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
    # sentiment
    "LABEL2ID",
    "ID2LABEL",
    "train",
    "predict_batch",
    "run_batch_inference",
]
