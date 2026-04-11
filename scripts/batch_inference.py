"""
Batch Sentiment Inference

Loads a fine-tuned DistilBERT model and runs inference on all unscored
preprocessed records, writing predictions to the `sentiment_predictions` table.

Usage:
    python scripts/batch_inference.py \
        --db reddit_data.db \
        --model-dir models/sentiment_v1
"""

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Run batch sentiment inference")
    parser.add_argument("--db", default="reddit_data.db", help="Path to SQLite database")
    parser.add_argument(
        "--model-dir",
        default="models/sentiment_v1",
        help="Path to fine-tuned DistilBERT model directory",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=1000,
        help="Records per DB batch (default: 1000)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Process at most N records (for testing)",
    )
    args = parser.parse_args()

    model_dir = Path(args.model_dir)
    if not model_dir.exists():
        logger.error("Model directory not found: %s", model_dir)
        sys.exit(1)

    from src.ml.sentiment import run_batch_inference

    logger.info("Starting batch inference: db=%s model=%s", args.db, args.model_dir)
    result = run_batch_inference(
        db_path=args.db,
        model_dir=args.model_dir,
        batch_size=args.batch_size,
    )

    total = result["total_scored"]
    pos = result["positive_count"]
    neu = result["neutral_count"]
    neg = result["negative_count"]

    print(f"\n{'='*50}")
    print(f"Inference complete")
    print(f"Total scored:  {total:,}")
    if total:
        print(f"  Positive:    {pos:,} ({pos/total*100:.1f}%)")
        print(f"  Neutral:     {neu:,} ({neu/total*100:.1f}%)")
        print(f"  Negative:    {neg:,} ({neg/total*100:.1f}%)")
    print(f"Model:         {args.model_dir}")
    print(f"Device:        {result['device']}")
    print(f"{'='*50}\n")


if __name__ == "__main__":
    main()
