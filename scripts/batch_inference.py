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
        default=None,
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
    parser.add_argument(
        "--rescore-existing",
        action="store_true",
        help="Explicitly replace predictions from an older model fingerprint",
    )
    parser.add_argument("--train-candidate", action="store_true")
    parser.add_argument("--promote-candidate", action="store_true")
    args = parser.parse_args()

    from src.ml.sentiment import pipeline_candidate_dir, pipeline_model_dir, run_batch_inference, train_pipeline_candidate

    if args.train_candidate:
        result = train_pipeline_candidate(args.db)
        print(f"Val F1 (macro): {result['val_f1']:.4f}")
        return

    candidate = pipeline_candidate_dir(args.db) if args.promote_candidate else None
    args.model_dir = candidate or args.model_dir or pipeline_model_dir(args.db)

    model_dir = Path(args.model_dir)
    if not model_dir.exists():
        logger.error("Model directory not found: %s", model_dir)
        sys.exit(1)

    logger.info("Starting batch inference: db=%s model=%s", args.db, args.model_dir)
    result = run_batch_inference(
        db_path=args.db,
        model_dir=args.model_dir,
        batch_size=args.batch_size,
        rescore_existing=args.rescore_existing or bool(candidate),
        promote_candidate=bool(candidate),
    )

    total = result["total_scored"]
    pos = result["positive_count"]
    neu = result["neutral_count"]
    neg = result["negative_count"]

    print(f"\n{'='*50}")
    print("Inference complete")
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
