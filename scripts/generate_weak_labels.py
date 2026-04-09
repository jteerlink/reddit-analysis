"""
Generate Weak Sentiment Labels via VADER

Reads the `preprocessed` table, scores each record with VADER, and writes
a labeled CSV for high-confidence examples (|compound| > threshold).

Usage:
    python scripts/generate_weak_labels.py \
        --db reddit_data.db \
        --output data/weak_labels.csv \
        --threshold 0.5
"""

import argparse
import csv
import logging
import sys
from pathlib import Path

# Allow running from project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Generate VADER weak labels")
    parser.add_argument("--db", default="reddit_data.db", help="Path to SQLite database")
    parser.add_argument("--output", default="data/weak_labels.csv", help="Output CSV path")
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.5,
        help="VADER compound score threshold (default 0.5)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max records to process (default: all)",
    )
    args = parser.parse_args()

    mlflow_run = None
    try:
        import mlflow
        mlflow.set_tracking_uri("mlruns")
        mlflow.set_experiment("reddit-analyzer-phase2")
        mlflow_run = mlflow.start_run(run_name="week1-weak-labels")
    except ImportError:
        logger.warning("mlflow not installed; skipping tracking")

    from src.ml.db import get_connection

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    conn = get_connection(args.db)
    analyzer = SentimentIntensityAnalyzer()

    query = """
        SELECT p.id, p.content_type, p.clean_text,
               COALESCE(
                   (SELECT subreddit FROM posts WHERE posts.id = p.id),
                   (SELECT subreddit FROM comments WHERE comments.id = p.id)
               ) AS subreddit
        FROM preprocessed p
        WHERE p.is_filtered = 0
          AND p.clean_text IS NOT NULL
          AND p.clean_text != ''
    """
    if args.limit:
        query += f" LIMIT {args.limit}"

    cursor = conn.execute(query)

    total_scored = 0
    kept = 0
    positive = 0
    negative = 0

    with open(output_path, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(["id", "content_type", "subreddit", "clean_text", "vader_compound", "label"])

        for row in cursor:
            total_scored += 1
            scores = analyzer.polarity_scores(row["clean_text"])
            compound = scores["compound"]

            if abs(compound) <= args.threshold:
                continue

            label = "positive" if compound > 0 else "negative"
            writer.writerow([
                row["id"],
                row["content_type"],
                row["subreddit"] or "",
                row["clean_text"],
                round(compound, 4),
                label,
            ])
            kept += 1
            if label == "positive":
                positive += 1
            else:
                negative += 1

            if total_scored % 10000 == 0:
                logger.info("Scored %d records, kept %d so far", total_scored, kept)

    conn.close()

    gate_ok = kept >= 30000
    print(f"\n{'='*50}")
    print(f"Total scored:    {total_scored:,}")
    print(f"Kept (|score| > {args.threshold}): {kept:,}")
    print(f"  Positive:      {positive:,} ({positive/kept*100:.1f}%)" if kept else "  Positive: 0")
    print(f"  Negative:      {negative:,} ({negative/kept*100:.1f}%)" if kept else "  Negative: 0")
    print(f"Output:          {output_path}")
    print(f"\nGate (≥30k):     {'PASS ✓' if gate_ok else 'FAIL ✗ — collect more data or lower threshold'}")
    print(f"{'='*50}\n")

    if mlflow_run is not None:
        import mlflow
        mlflow.log_params({"threshold": args.threshold, "db": args.db})
        mlflow.log_metrics({
            "total_scored": total_scored,
            "kept_count": kept,
            "positive_count": positive,
            "negative_count": negative,
        })
        mlflow.end_run()

    sys.exit(0 if gate_ok else 1)


if __name__ == "__main__":
    main()
