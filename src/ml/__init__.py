"""
Reddit Analyzer — ML Layer

Phase 2 machine learning pipeline: preprocessing, sentiment, topic modeling,
and time series analysis.
"""

from .preprocessing import EmbeddingGenerator, TextCleaner, run_preprocessing
from .db import get_connection, ensure_preprocessed_table, iter_raw_records, upsert_preprocessed

__all__ = [
    "TextCleaner",
    "EmbeddingGenerator",
    "run_preprocessing",
    "get_connection",
    "ensure_preprocessed_table",
    "iter_raw_records",
    "upsert_preprocessed",
]
