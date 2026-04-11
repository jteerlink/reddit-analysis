#!/usr/bin/env python3
"""Train BERTopic topic model on a rolling window of Reddit data."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.ml.topics import run_topic_modeling


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Train BERTopic on preprocessed Reddit data."
    )
    parser.add_argument(
        "--db", default="historical_reddit_data.db", help="Path to SQLite database"
    )
    parser.add_argument(
        "--cache-dir", default="models/", help="Directory containing embedding cache"
    )
    parser.add_argument(
        "--days", type=int, default=90, help="Rolling window in days (default: 90)"
    )
    parser.add_argument(
        "--batch-size", type=int, default=1000, help="DB read batch size"
    )
    parser.add_argument(
        "--nr-topics",
        default="auto",
        help='Max topics cap or "auto" to let HDBSCAN decide (default: auto)',
    )
    parser.add_argument(
        "--min-cluster-size",
        type=int,
        default=30,
        help="HDBSCAN min_cluster_size (default: 30)",
    )
    parser.add_argument(
        "--min-topic-size",
        type=int,
        default=30,
        help="BERTopic min_topic_size (default: 30)",
    )
    parser.add_argument(
        "--skip-gate",
        action="store_true",
        help="Write results and exit 0 even if the coherence gate fails",
    )
    parser.add_argument(
        "--no-mlflow", action="store_true", help="Disable MLflow experiment tracking"
    )
    args = parser.parse_args()

    if not Path(args.db).exists():
        print(f"Error: database not found at {args.db}", file=sys.stderr)
        sys.exit(1)

    nr_topics: object = args.nr_topics if args.nr_topics == "auto" else int(args.nr_topics)

    result = run_topic_modeling(
        db_path=args.db,
        cache_dir=args.cache_dir,
        days=args.days,
        batch_size=args.batch_size,
        min_cluster_size=args.min_cluster_size,
        nr_topics=nr_topics,
        min_topic_size=args.min_topic_size,
        mlflow_tracking=not args.no_mlflow,
        skip_gate_check=args.skip_gate,
    )

    total = result["total_docs"]
    n_topics = result["n_topics"]
    n_out = result["n_outliers"]
    out_pct = f"{100 * n_out / total:.1f}" if total > 0 else "0.0"
    gate = "PASSED" if result["gate_passed"] else "FAILED"

    print("=" * 50)
    print("Topic Modeling Complete")
    print(f"Total documents:    {total:,}")
    print(f"Topics discovered:  {n_topics}  (excluding outliers)")
    print(f"Outlier documents:  {n_out:,}  ({out_pct}%)")
    print(f"Coherent topics:    {result['coherent_topic_count']}  (coherence >= 0.50)")
    print(f"Mean coherence:     {result['mean_coherence']:.2f}")
    print(f"Gate:               {gate} (>= 20 coherent topics required)")
    print(f"Device:             {result['device']}")
    print(f"Window:             {args.days} days")
    print("=" * 50)

    if not result["gate_passed"] and not args.skip_gate:
        sys.exit(1)


if __name__ == "__main__":
    main()
