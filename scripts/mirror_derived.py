"""Atomically publish a complete derived-data snapshot to the optional mirror."""

from typing import Any, Callable, Mapping

import pandas as pd

# Raw collection and historical artifact/audit tables are deliberately excluded.
DERIVED_TABLES = (
    "sentiment_predictions", "topics", "topic_assignments", "topic_over_time",
    "sentiment_daily", "sentiment_moving_avg", "change_points",
    "sentiment_forecast", "topic_sentiment_trends", "embedding_2d", "cluster_labels",
)


def publish_snapshot(
    connection: Any,
    frames: Mapping[str, pd.DataFrame],
    insert_batch: Callable,
    reconnect: Callable,
    operational_error: type[Exception],
    batch_size: int,
) -> Any:
    """Replace derived tables in one transaction, retrying the entire snapshot.

    A disconnect must never commit only the first part of a new model generation.
    Empty source tables intentionally clear their corresponding derived mirror.
    Missing source tables, raw records, and audit history remain untouched.
    """
    if batch_size < 1 or not set(frames).issubset(DERIVED_TABLES):
        raise ValueError("Invalid derived snapshot or batch size")
    for attempt in range(3):
        try:
            with connection.cursor() as cursor:
                for table in reversed(DERIVED_TABLES):
                    if table in frames:
                        cursor.execute(f'DELETE FROM "{table}"')
            for table in DERIVED_TABLES:
                if table not in frames:
                    continue
                frame = frames[table]
                for start in range(0, len(frame), batch_size):
                    insert_batch(connection, table, frame.iloc[start:start + batch_size])
            connection.commit()
            return connection
        except operational_error:
            connection.close()
            if attempt == 2:
                raise
            connection = reconnect()
            batch_size = max(1, batch_size // 2)
        except Exception:
            connection.rollback()
            connection.close()
            raise
    raise AssertionError("Unreachable snapshot retry state")
