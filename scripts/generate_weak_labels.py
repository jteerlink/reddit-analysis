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
    parser.add_argument(
        "--include-neutral",
        action="store_true",
        default=False,
        help="Include neutral examples (|compound| < --neutral-threshold) for 3-class labeling",
    )
    parser.add_argument(
        "--neutral-threshold",
        type=float,
        default=0.1,
        help="VADER compound threshold for neutral label (default 0.1)",
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
    from src.db.connection import is_postgres_connection

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    conn = get_connection(args.db)
    analyzer = SentimentIntensityAnalyzer()

    query = f"""
        SELECT p.id, p.content_type, p.clean_text,
               COALESCE(
                   (SELECT subreddit FROM posts WHERE posts.id = p.id),
                   (SELECT subreddit FROM comments WHERE comments.id = p.id)
               ) AS subreddit
        FROM preprocessed p
        WHERE p.is_filtered = {'FALSE' if is_postgres_connection(conn) else '0'}
          AND p.clean_text IS NOT NULL
          AND p.clean_text != ''
    """
    if args.limit:
        query += f" LIMIT {args.limit}"

    if is_postgres_connection(conn):
        cursor = conn.cursor()
        cursor.execute(query)
    else:
        cursor = conn.execute(query)

    # Collect labeled rows; neutral candidates held separately for balancing
    positive_rows = []
    negative_rows = []
    neutral_candidates = []
    total_scored = 0

    for row in cursor:
        total_scored += 1
        scores = analyzer.polarity_scores(row["clean_text"])
        compound = scores["compound"]
        rec = (row["id"], row["content_type"], row["subreddit"] or "", row["clean_text"], round(compound, 4))

        if compound > args.threshold:
            positive_rows.append(rec)
        elif compound < -args.threshold:
            negative_rows.append(rec)
        elif args.include_neutral and abs(compound) < args.neutral_threshold:
            neutral_candidates.append(rec)

        if total_scored % 10000 == 0:
            logger.info("Scored %d records so far", total_scored)

    conn.close()

    # Balance neutral sample to minority class size
    if args.include_neutral and neutral_candidates:
        import random
        minority = min(len(positive_rows), len(negative_rows))
        sample_size = min(len(neutral_candidates), minority)
        random.seed(42)
        neutral_rows = random.sample(neutral_candidates, sample_size)
    else:
        neutral_rows = []

    with open(output_path, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(["id", "content_type", "subreddit", "clean_text", "vader_compound", "label"])
        for rec in positive_rows:
            writer.writerow([*rec, "positive"])
        for rec in negative_rows:
            writer.writerow([*rec, "negative"])
        for rec in neutral_rows:
            writer.writerow([*rec, "neutral"])

    kept = len(positive_rows) + len(negative_rows) + len(neutral_rows)
    positive = len(positive_rows)
    negative = len(negative_rows)
    neutral = len(neutral_rows)

    gate_ok = kept >= 30000
    print(f"\n{'='*50}")
    print(f"Total scored:    {total_scored:,}")
    print(f"Kept:            {kept:,}")
    print(f"  Positive:      {positive:,} ({positive/kept*100:.1f}%)" if kept else "  Positive: 0")
    print(f"  Negative:      {negative:,} ({negative/kept*100:.1f}%)" if kept else "  Negative: 0")
    if args.include_neutral:
        print(f"  Neutral:       {neutral:,} ({neutral/kept*100:.1f}%)" if kept else "  Neutral: 0")
    print(f"Output:          {output_path}")
    print(f"\nGate (≥30k):     {'PASS ✓' if gate_ok else 'FAIL ✗ — collect more data or lower threshold'}")
    print(f"{'='*50}\n")

    if mlflow_run is not None:
        import mlflow
        mlflow.log_params({
            "threshold": args.threshold,
            "include_neutral": args.include_neutral,
            "neutral_threshold": args.neutral_threshold,
            "db": args.db,
        })
        mlflow.log_metrics({
            "total_scored": total_scored,
            "kept_count": kept,
            "positive_count": positive,
            "negative_count": negative,
            "neutral_count": neutral,
        })
        mlflow.end_run()

    sys.exit(0 if gate_ok else 1)


if __name__ == "__main__":
    main()
