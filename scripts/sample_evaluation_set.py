#!/usr/bin/env python3
"""Create a deterministic, annotation-ready sentiment evaluation sample.

The output deliberately leaves ``human_label`` empty.  VADER and any existing
model prediction are context for annotators, never an independent reference
label.  A JSON manifest next to the CSV records the sampling and holdout rules.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer


LABELS = ("negative", "neutral", "positive")
OUTPUT_FIELDS = (
    "id",
    "content_type",
    "subreddit",
    "thread_id",
    "timestamp",
    "time_stratum",
    "holdout_split",
    "original_title",
    "original_text",
    "source_url",
    "human_label",
    "annotation_notes",
)
REFERENCE_FIELDS = (
    "id", "content_type", "clean_text", "vader_compound", "vader_label", "model_label",
    "model_confidence",
)


def _vader_label(compound: float) -> str:
    if compound >= 0.05:
        return "positive"
    if compound <= -0.05:
        return "negative"
    return "neutral"


def _thread_bucket(thread_id: str) -> int:
    digest = hashlib.sha256(thread_id.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % 5


def _time_value(value: object) -> datetime | None:
    if value in (None, ""):
        return None
    text = str(value).replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed
    except ValueError:
        return None


def _time_stratum(value: object, cutoffs: tuple[datetime, ...]) -> str:
    parsed = _time_value(value)
    if parsed is None:
        return "unknown"
    for index, cutoff in enumerate(cutoffs):
        if parsed <= cutoff:
            return f"q{index + 1}"
    return f"q{len(cutoffs) + 1}"


def _quantile_cutoffs(values: list[datetime], bins: int = 4) -> tuple[datetime, ...]:
    if not values:
        return ()
    ordered = sorted(values)
    return tuple(ordered[min(len(ordered) - 1, math.ceil(len(ordered) * i / bins) - 1)] for i in range(1, bins))


def _load_rows(db_path: str) -> list[dict]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    has_predictions = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='sentiment_predictions'"
    ).fetchone()
    prediction_join = "LEFT JOIN sentiment_predictions sp ON sp.id = p.id AND sp.content_type = p.content_type" if has_predictions else ""
    prediction_columns = (
        "sp.label AS model_label, sp.confidence AS model_confidence"
        if has_predictions
        else "NULL AS model_label, NULL AS model_confidence"
    )
    query = f"""
        SELECT p.id, p.content_type, p.clean_text,
               COALESCE(posts.subreddit, comments.subreddit, '') AS subreddit,
               COALESCE(posts.timestamp, comments.timestamp) AS timestamp,
               COALESCE(posts.title, '') AS original_title,
               COALESCE(posts.content, comments.content, p.raw_text, '') AS original_text,
               COALESCE(posts.url, '') AS source_url,
               CASE
                 WHEN p.content_type = 'post' THEN p.id
                 ELSE COALESCE(comments.post_id, comments.parent_id, comments.id)
               END AS thread_id,
               {prediction_columns}
        FROM preprocessed p
        LEFT JOIN posts ON p.content_type = 'post' AND posts.id = p.id
        LEFT JOIN comments ON p.content_type = 'comment' AND comments.id = p.id
        {prediction_join}
        WHERE p.is_filtered = 0 AND p.clean_text IS NOT NULL AND TRIM(p.clean_text) != ''
        ORDER BY p.id, p.content_type
    """
    try:
        return [dict(row) for row in conn.execute(query)]
    finally:
        conn.close()


def _round_robin_sample(rows: list[dict], size: int) -> list[dict]:
    """Take one row per joint stratum repeatedly, with stable ordering."""
    strata: dict[tuple[str, str, str, str], list[dict]] = defaultdict(list)
    for row in rows:
        key = (
            str(row["subreddit"] or ""),
            str(row["time_stratum"]),
            str(row["vader_label"]),
            str(row["content_type"]),
        )
        strata[key].append(row)
    for values in strata.values():
        values.sort(key=lambda item: str(item["id"]))

    selected: list[dict] = []
    keys = sorted(strata)
    index = 0
    while len(selected) < size and keys:
        next_keys = []
        for key in keys:
            values = strata[key]
            if index < len(values) and len(selected) < size:
                selected.append(values[index])
            if index + 1 < len(values):
                next_keys.append(key)
        keys = next_keys
        index += 1
    return selected


def build_sample(rows: Iterable[dict], size: int = 250) -> tuple[list[dict], dict]:
    """Annotate source rows and return a deterministic sample plus manifest."""
    if size < 1:
        raise ValueError("size must be positive")
    source = [dict(row) for row in rows]
    if not source:
        return [], {"requested_size": size, "sample_size": 0, "status": "no_data"}

    analyzer = SentimentIntensityAnalyzer()
    timestamps = [parsed for parsed in (_time_value(row.get("timestamp")) for row in source) if parsed]
    cutoffs = _quantile_cutoffs(timestamps)
    for row in source:
        compound = analyzer.polarity_scores(str(row.get("clean_text") or ""))["compound"]
        row["vader_compound"] = round(float(compound), 4)
        row["vader_label"] = _vader_label(float(compound))
        row["time_stratum"] = _time_stratum(row.get("timestamp"), cutoffs)
        row["thread_id"] = str(row.get("thread_id") or row["id"])

    selected = _round_robin_sample(source, min(size, len(source)))
    latest = max(timestamps) if timestamps else None
    earliest = min(timestamps) if timestamps else None
    temporal_cutoff = None
    if earliest and latest:
        temporal_cutoff = earliest + (latest - earliest) * 0.8

    for row in selected:
        parsed = _time_value(row.get("timestamp"))
        temporal_holdout = bool(parsed and temporal_cutoff and parsed >= temporal_cutoff)
        thread_holdout = _thread_bucket(row["thread_id"]) == 0
        row["holdout_split"] = "holdout" if temporal_holdout or thread_holdout else "development"

    counts = Counter(row["holdout_split"] for row in selected)
    manifest = {
        "status": "unverified_until_human_labels",
        "requested_size": size,
        "sample_size": len(selected),
        "seed": "sha256(id), stable source-id ordering",
        "strata": ["subreddit", "time_stratum", "vader_label", "content_type"],
        "time_strata": "quartiles over available source timestamps; unknown is retained",
        "holdout": "latest 20% of timestamp range OR sha256(thread_id) bucket 0/5",
        "human_label_policy": "human_label is blank until independent review; no labels are fabricated",
        "split_counts": dict(sorted(counts.items())),
        "label_counts": dict(sorted(Counter(row["vader_label"] for row in selected).items())),
    }
    return selected, manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="historical_reddit_data.db", help="SQLite database path")
    parser.add_argument("--output", default="data/sentiment_evaluation_sample.csv", help="CSV output path")
    parser.add_argument("--size", type=int, default=250, help="Requested sample size (default: 250)")
    args = parser.parse_args()
    if not Path(args.db).exists():
        parser.error(f"database not found: {args.db}")

    selected, manifest = build_sample(_load_rows(args.db), args.size)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        for row in selected:
            writer.writerow({field: row.get(field, "") for field in OUTPUT_FIELDS})
    reference_output = output.with_name(f"{output.stem}_reference.csv")
    with reference_output.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=REFERENCE_FIELDS)
        writer.writeheader()
        for row in selected:
            writer.writerow({field: row.get(field, "") for field in REFERENCE_FIELDS})
    manifest["output"] = str(output)
    manifest["reference_output"] = str(reference_output)
    output.with_suffix(".meta.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
