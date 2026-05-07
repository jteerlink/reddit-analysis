"""
ML Layer — DistilBERT Sentiment Fine-Tuning & Inference

Fine-tunes distilbert-base-uncased on VADER-generated weak labels for
3-class sentiment classification (positive / neutral / negative).
Uses MPS on Apple Silicon for hardware-accelerated training and inference.
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)

LABEL2ID = {"negative": 0, "neutral": 1, "positive": 2}
ID2LABEL = {v: k for k, v in LABEL2ID.items()}


def _detect_device() -> str:
    """Return the best available PyTorch device: mps → cuda → cpu."""
    try:
        import torch
        if torch.backends.mps.is_available():
            return "mps"
        if torch.cuda.is_available():
            return "cuda"
    except ImportError:
        pass
    return "cpu"


class _SentimentDataset:
    """Minimal torch Dataset wrapping tokenized inputs + integer labels."""

    def __init__(self, encodings, labels):
        self._encodings = encodings
        self._labels = labels

    def __len__(self):
        return len(self._labels)

    def __getitem__(self, idx):
        import torch
        item = {k: torch.tensor(v[idx]) for k, v in self._encodings.items()}
        item["labels"] = torch.tensor(self._labels[idx], dtype=torch.long)
        return item


def _compute_metrics(eval_pred):
    from sklearn.metrics import f1_score
    import numpy as np
    logits, labels = eval_pred
    preds = np.argmax(logits, axis=-1)
    macro_f1 = f1_score(labels, preds, average="macro", zero_division=0)
    per_class = f1_score(labels, preds, average=None, zero_division=0, labels=[0, 1, 2])
    return {
        "f1": macro_f1,
        "f1_negative": per_class[0],
        "f1_neutral": per_class[1],
        "f1_positive": per_class[2],
    }


def _log_validation_metrics_to_mlflow(summary: Dict) -> None:
    import mlflow

    metrics_to_log = {
        "val_f1_positive": summary["val_f1_positive"],
        "val_f1_negative": summary["val_f1_negative"],
        "val_f1_neutral": summary["val_f1_neutral"],
    }
    active_run = mlflow.active_run()
    if active_run is not None:
        mlflow.log_metrics(metrics_to_log)
        return

    last_run = mlflow.last_active_run()
    if last_run is not None:
        with mlflow.start_run(run_id=last_run.info.run_id):
            mlflow.log_metrics(metrics_to_log)


def train(
    weak_labels_path: str,
    model_dir: str,
    val_split: float = 0.2,
    epochs: int = 3,
    lr: float = 2e-5,
    batch_size: int = 16,
    max_length: int = 256,
    mlflow_tracking: bool = True,
) -> Dict:
    """
    Fine-tune distilbert-base-uncased on the weak labels CSV.

    Args:
        weak_labels_path: Path to CSV with columns [id, content_type, subreddit,
                          clean_text, vader_compound, label].
        model_dir: Directory to save the fine-tuned model + tokenizer.
        val_split: Fraction of data held out for validation.
        epochs: Number of training epochs.
        lr: Learning rate.
        batch_size: Per-device training batch size.
        max_length: Tokenizer max token length (truncated).
        mlflow_tracking: Whether to log to MLflow.

    Returns:
        Summary dict with val_f1, model_dir, device, and per-class F1s.
    """
    import pandas as pd
    from sklearn.model_selection import train_test_split
    from transformers import (
        DistilBertForSequenceClassification,
        DistilBertTokenizerFast,
        Trainer,
        TrainingArguments,
    )

    device = _detect_device()
    logger.info("Training on device=%s", device)

    df = pd.read_csv(weak_labels_path)
    if "label" not in df.columns or "clean_text" not in df.columns:
        raise ValueError("weak_labels CSV must have 'clean_text' and 'label' columns")

    df = df.dropna(subset=["clean_text", "label"])
    df = df[df["label"].isin(LABEL2ID)]
    df["label_id"] = df["label"].map(LABEL2ID)

    texts = df["clean_text"].tolist()
    labels = df["label_id"].tolist()

    train_texts, val_texts, train_labels, val_labels = train_test_split(
        texts, labels, test_size=val_split, stratify=labels, random_state=42
    )
    logger.info("Train: %d, Val: %d", len(train_texts), len(val_texts))

    tokenizer = DistilBertTokenizerFast.from_pretrained("distilbert-base-uncased")

    train_enc = tokenizer(train_texts, truncation=True, padding=True, max_length=max_length)
    val_enc = tokenizer(val_texts, truncation=True, padding=True, max_length=max_length)

    train_dataset = _SentimentDataset(train_enc, train_labels)
    val_dataset = _SentimentDataset(val_enc, val_labels)

    model = DistilBertForSequenceClassification.from_pretrained(
        "distilbert-base-uncased",
        num_labels=3,
        id2label=ID2LABEL,
        label2id=LABEL2ID,
    )

    output_dir = Path(model_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if mlflow_tracking:
        try:
            import mlflow
            mlflow.set_tracking_uri(str(Path(model_dir).parent.parent / "mlruns"))
            mlflow.set_experiment("reddit-analyzer-phase2")
        except ImportError:
            logger.warning("mlflow not installed; skipping experiment tracking")
            mlflow_tracking = False

    training_args_kwargs = dict(
        output_dir=str(output_dir),
        num_train_epochs=epochs,
        per_device_train_batch_size=batch_size,
        per_device_eval_batch_size=batch_size * 2,
        learning_rate=lr,
        weight_decay=0.01,
        warmup_steps=100,
        eval_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,
        metric_for_best_model="f1",
        greater_is_better=True,
        logging_steps=50,
        run_name="week2-sentiment-train",
        report_to="mlflow" if mlflow_tracking else "none",
        fp16=False,
    )

    training_args = TrainingArguments(**training_args_kwargs)

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=val_dataset,
        compute_metrics=_compute_metrics,
    )

    trainer.train()
    metrics = trainer.evaluate()
    logger.info("Validation metrics: %s", metrics)

    trainer.save_model(str(output_dir))
    tokenizer.save_pretrained(str(output_dir))

    summary = {
        "val_f1": metrics.get("eval_f1", 0.0),
        "val_f1_positive": metrics.get("eval_f1_positive", 0.0),
        "val_f1_negative": metrics.get("eval_f1_negative", 0.0),
        "val_f1_neutral": metrics.get("eval_f1_neutral", 0.0),
        "val_loss": metrics.get("eval_loss", 0.0),
        "model_dir": str(output_dir),
        "device": device,
        "train_size": len(train_texts),
        "val_size": len(val_texts),
    }

    if mlflow_tracking:
        try:
            _log_validation_metrics_to_mlflow(summary)
        except ImportError:
            logger.warning("mlflow not installed; skipping experiment tracking")

    return summary


def predict_batch(
    texts: List[str],
    model_dir: str,
    batch_size: int = 64,
    device: Optional[str] = None,
) -> List[Dict]:
    """
    Run inference on a list of texts using a saved fine-tuned model.

    Returns a list of dicts: {label: str, confidence: float, logits: list[float]}
    """
    import torch
    from transformers import DistilBertForSequenceClassification, DistilBertTokenizerFast

    if device is None:
        device = _detect_device()

    tokenizer = DistilBertTokenizerFast.from_pretrained(model_dir)
    model = DistilBertForSequenceClassification.from_pretrained(model_dir)
    model.to(device)
    model.eval()

    results = []
    for start in range(0, len(texts), batch_size):
        chunk = texts[start: start + batch_size]
        enc = tokenizer(
            chunk,
            truncation=True,
            padding=True,
            max_length=256,
            return_tensors="pt",
        )
        enc = {k: v.to(device) for k, v in enc.items()}

        with torch.no_grad():
            outputs = model(**enc)

        logits = outputs.logits.cpu().float().numpy()
        probs = _softmax(logits)

        for row_logits, row_probs in zip(logits, probs):
            pred_id = int(np.argmax(row_probs))
            results.append({
                "label": ID2LABEL[pred_id],
                "confidence": float(row_probs[pred_id]),
                "logits": row_logits.tolist(),
            })

    return results


def _softmax(x: np.ndarray) -> np.ndarray:
    e = np.exp(x - x.max(axis=-1, keepdims=True))
    return e / e.sum(axis=-1, keepdims=True)


def run_batch_inference(
    db_path: str,
    model_dir: str,
    batch_size: int = 1000,
    mlflow_tracking: bool = True,
) -> Dict:
    """
    Batch-inference orchestrator: score all unscored preprocessed records.

    Reads from `preprocessed` (is_filtered=0) where no prediction exists,
    writes results to `sentiment_predictions`.
    """
    from .db import get_connection, ensure_sentiment_table, iter_unscored_records, upsert_sentiment

    device = _detect_device()
    model_version = str(Path(model_dir).resolve())

    conn = get_connection(db_path)
    ensure_sentiment_table(conn)

    total = positive = neutral = negative = 0

    for batch in iter_unscored_records(conn, batch_size=batch_size):
        ids = [r["id"] for r in batch]
        content_types = [r["content_type"] for r in batch]
        texts = [r["clean_text"] for r in batch]

        preds = predict_batch(texts, model_dir, batch_size=min(64, batch_size), device=device)

        rows = []
        for rid, ct, pred in zip(ids, content_types, preds):
            rows.append((
                rid,
                ct,
                pred["label"],
                pred["confidence"],
                json.dumps(pred["logits"]),
                model_version,
            ))
            if pred["label"] == "positive":
                positive += 1
            elif pred["label"] == "negative":
                negative += 1
            else:
                neutral += 1

        upsert_sentiment(conn, rows)
        total += len(rows)
        logger.info("Inference batch done — total scored=%d", total)

    conn.close()

    summary = {
        "total_scored": total,
        "positive_count": positive,
        "neutral_count": neutral,
        "negative_count": negative,
        "model_version": model_version,
        "device": device,
    }

    if mlflow_tracking:
        try:
            import mlflow
            mlflow.set_tracking_uri("mlruns")
            mlflow.set_experiment("reddit-analyzer-phase2")
            with mlflow.start_run(run_name="week2-batch-inference"):
                mlflow.log_params({"model_version": model_version, "device": device})
                mlflow.log_metrics({
                    "total_scored": total,
                    "positive_count": positive,
                    "neutral_count": neutral,
                    "negative_count": negative,
                })
        except ImportError:
            logger.warning("mlflow not installed; skipping experiment tracking")

    logger.info("Batch inference complete: %s", summary)
    return summary
