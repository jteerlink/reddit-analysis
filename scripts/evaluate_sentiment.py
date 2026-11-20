#!/usr/bin/env python3
"""Evaluate existing sentiment predictions against independently reviewed labels.

This command never trains or promotes a model.  Until ``human_label`` values
are entered in the sample CSV it reports an explicit unverified status.
"""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from pathlib import Path
from typing import Iterable

LABELS = {"negative", "neutral", "positive"}


def _read_sample(path: str) -> list[dict[str, str]]:
    with Path(path).open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def _merge_reference(rows: list[dict[str, str]], reference_path: str | None) -> list[dict[str, str]]:
    if not reference_path:
        return rows
    reference = {row.get("id", ""): row for row in _read_sample(reference_path)}
    merged = []
    for row in rows:
        combined = dict(reference.get(row.get("id", ""), {}))
        combined.update(row)
        merged.append(combined)
    return merged


def _predictions(db_path: str, ids: list[str]) -> dict[str, dict]:
    if not ids or not Path(db_path).exists():
        return {}
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        marks = ",".join("?" for _ in ids)
        return {
            row["id"]: dict(row)
            for row in conn.execute(
                f"SELECT id, label, confidence, model_version FROM sentiment_predictions WHERE id IN ({marks})",
                ids,
            )
        }
    finally:
        conn.close()


def _f1_by_label(y_true: list[str], y_pred: list[str], label: str) -> float:
    tp = sum(actual == label and predicted == label for actual, predicted in zip(y_true, y_pred))
    fp = sum(actual != label and predicted == label for actual, predicted in zip(y_true, y_pred))
    fn = sum(actual == label and predicted != label for actual, predicted in zip(y_true, y_pred))
    if tp == 0:
        return 0.0
    return 2 * tp / (2 * tp + fp + fn)


def _metrics(y_true: list[str], y_pred: list[str]) -> dict:
    per_class = {label: _f1_by_label(y_true, y_pred, label) for label in sorted(LABELS)}
    return {
        "sample_size": len(y_true),
        "accuracy": sum(a == p for a, p in zip(y_true, y_pred)) / len(y_true) if y_true else None,
        "macro_f1": sum(per_class.values()) / len(per_class) if y_true else None,
        "f1_by_class": per_class,
        "confusion": {
            actual: {predicted: sum(a == actual and p == predicted for a, p in zip(y_true, y_pred)) for predicted in sorted(LABELS)}
            for actual in sorted(LABELS)
        },
    }


def evaluate_rows(rows: Iterable[dict[str, str]], prediction_rows: dict[str, dict] | None = None) -> dict:
    rows = list(rows)
    prediction_rows = prediction_rows or {}
    reviewed = []
    missing_predictions = []
    for row in rows:
        human = str(row.get("human_label") or "").strip().lower()
        if human not in LABELS:
            continue
        prediction = row.get("model_label") or prediction_rows.get(str(row.get("id")), {}).get("label")
        if prediction not in LABELS:
            missing_predictions.append(str(row.get("id", "")))
            continue
        vader = str(row.get("vader_label") or "").strip().lower()
        reviewed.append((row, human, str(prediction), vader if vader in LABELS else None))

    result = {
        "status": "verified" if reviewed else "unverified",
        "independent_evaluation": bool(reviewed),
        "human_label_count": len(reviewed),
        "missing_human_label_count": sum(1 for row in rows if str(row.get("human_label") or "").strip().lower() not in LABELS),
        "missing_prediction_ids": missing_predictions,
        "model_versions": sorted({str(prediction_rows.get(str(row.get("id")), {}).get("model_version")) for row, _, _, _ in reviewed if prediction_rows.get(str(row.get("id")), {}).get("model_version")}),
        "metrics": None,
        "vader_agreement": None,
        "errors": [],
        "promotion": {"eligible": False, "reason": "human labels are required and no automatic promotion is performed"},
    }
    if not reviewed:
        return result

    y_true = [human for _, human, _, _ in reviewed]
    y_pred = [prediction for _, _, prediction, _ in reviewed]
    result["metrics"] = _metrics(y_true, y_pred)
    vader_pairs = [(human, vader) for _, human, _, vader in reviewed if vader]
    result["vader_agreement"] = {
        "sample_size": len(vader_pairs),
        "agreement": sum(a == b for a, b in vader_pairs) / len(vader_pairs) if vader_pairs else None,
        "label": "agreement with VADER, not accuracy unless human labels are the reference",
    }
    errors = []
    for row, human, prediction, _ in reviewed:
        if human != prediction:
            errors.append({"id": row.get("id"), "human_label": human, "model_label": prediction, "text": row.get("clean_text", "")})
    result["errors"] = errors[:20]
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample", default="data/sentiment_evaluation_sample.csv", help="Annotation CSV")
    parser.add_argument("--reference", default=None, help="Optional blinded-sample reference CSV produced by sample_evaluation_set.py")
    parser.add_argument("--db", default="historical_reddit_data.db", help="SQLite database with existing predictions")
    parser.add_argument("--output", default="data/sentiment_evaluation.json", help="Metrics JSON output")
    args = parser.parse_args()
    rows = _merge_reference(_read_sample(args.sample), args.reference)
    prediction_rows = _predictions(args.db, [str(row.get("id", "")) for row in rows])
    result = evaluate_rows(rows, prediction_rows)
    result["sample"] = str(args.sample)
    result["rules"] = {"reference": "human_label", "classes": sorted(LABELS), "errors_max": 20}
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
