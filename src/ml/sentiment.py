"""
ML Layer — DistilBERT Sentiment Fine-Tuning & Inference

Fine-tunes distilbert-base-uncased on VADER-generated weak labels for
3-class sentiment classification (positive / neutral / negative).
Uses MPS on Apple Silicon for hardware-accelerated training and inference.
"""

import hashlib
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)

LABEL2ID = {"negative": 0, "neutral": 1, "positive": 2}
ID2LABEL = {v: k for k, v in LABEL2ID.items()}
SENTIMENT_PREPROCESSING_VERSION = "sentiment-text-v1:max_length=256"


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


def model_fingerprint(model_dir: str) -> str:
    """Identify inference artifacts by bytes, independently of their directory."""
    model_path = Path(model_dir)
    if not model_path.is_dir():
        raise FileNotFoundError(f"Sentiment model directory not found: {model_dir}")
    digest = hashlib.sha256(SENTIMENT_PREPROCESSING_VERSION.encode("utf-8"))
    for artifact in sorted(model_path.iterdir()):
        if artifact.is_file() and artifact.suffix in {".json", ".txt", ".bin", ".safetensors", ".model"}:
            digest.update(artifact.name.encode())
            with artifact.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def predict_batch(
    texts: List[str],
    model_dir: str,
    batch_size: int = 64,
    device: Optional[str] = None,
    runtime: Optional[Dict] = None,
) -> List[Dict]:
    """
    Run inference on a list of texts using a saved fine-tuned model.

    Returns a list of dicts: {label: str, confidence: float, logits: list[float]}
    """
    import torch
    from transformers import DistilBertForSequenceClassification, DistilBertTokenizerFast

    if device is None:
        device = _detect_device()

    if runtime is None:
        runtime = {}
    if not runtime:
        tokenizer = DistilBertTokenizerFast.from_pretrained(model_dir)
        model = DistilBertForSequenceClassification.from_pretrained(model_dir)
        model.to(device)
        model.eval()
        runtime.update(tokenizer=tokenizer, model=model)
    tokenizer, model = runtime["tokenizer"], runtime["model"]

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


def _stored_pipeline_model(db_path: str, *, candidate: bool) -> str | None:
    import os
    import sqlite3

    from .db import get_connection, _execute
    from src.db.connection import is_postgres_connection

    if db_path.startswith(("postgres://", "postgresql://")) or os.environ.get("DATABASE_URL"):
        conn = get_connection(db_path)
    else:
        path = Path(db_path).resolve()
        if not path.is_file():
            return None
        conn = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)
    table = "sentiment_model_candidate" if candidate else "sentiment_model_active"
    try:
        query = (f"SELECT to_regclass('{table}')" if is_postgres_connection(conn)
                 else f"SELECT name FROM sqlite_master WHERE name = '{table}'")
        exists = _execute(conn, query).fetchone()
        if exists and exists[0]:
            model = _execute(conn, f"SELECT model_dir FROM {table} WHERE slot = 1").fetchone()
            if model:
                return str(model[0])
        return None
    finally:
        conn.close()


def pipeline_model_dir(db_path: str) -> str:
    """Resolve the model published alongside the current predictions."""
    return _stored_pipeline_model(db_path, candidate=False) or "models/sentiment_v1"


def train_pipeline_candidate(db_path: str) -> dict:
    """Train in a new directory and stage a database-specific candidate."""
    from uuid import uuid4
    from .db import get_connection, _execute, _marker

    directory = Path("models/sentiment_generations") / uuid4().hex
    result = train("data/weak_labels.csv", str(directory), mlflow_tracking=True)
    if not result["val_f1"] >= 0.70:
        raise ValueError(f"Candidate validation F1 below 0.70: {result['val_f1']:.4f}")
    conn = get_connection(db_path)
    try:
        marker = _marker(conn)
        _execute(conn, """CREATE TABLE IF NOT EXISTS sentiment_model_candidate (
            slot INTEGER PRIMARY KEY, model_dir TEXT NOT NULL
        )""")
        _execute(conn, f"""INSERT INTO sentiment_model_candidate (slot, model_dir)
            VALUES (1, {marker}) ON CONFLICT (slot) DO UPDATE SET model_dir = excluded.model_dir""",
            (str(directory.resolve()),))
        conn.commit()
    finally:
        conn.close()
    return result


def pipeline_candidate_dir(db_path: str) -> str | None:
    return _stored_pipeline_model(db_path, candidate=True)


def run_batch_inference(
    db_path: str,
    model_dir: str,
    batch_size: int = 1000,
    mlflow_tracking: bool = True,
    rescore_existing: bool = False,
    promote_candidate: bool = False,
) -> Dict:
    """
    Batch-inference orchestrator: score all unscored preprocessed records.

    Reads from `preprocessed` (is_filtered=0) where no prediction exists,
    writes results to `sentiment_predictions`.
    """
    from .db import (get_connection, ensure_sentiment_table, _execute,
                     _executemany, _marker, _false, _json_value)
    from src.db.connection import is_postgres_connection

    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    device = _detect_device()
    model_version = model_fingerprint(model_dir)
    conn = get_connection(db_path)
    total = positive = neutral = negative = 0
    runtime: Dict = {}
    try:
        ensure_sentiment_table(conn)
        versions = {r[0] for r in _execute(conn,
                    "SELECT DISTINCT model_version FROM sentiment_predictions").fetchall()}
        if versions - {model_version} and not rescore_existing:
            raise ValueError("Model version changed; explicitly rescore_existing to promote it")
        # A private staging table keeps the published generation intact on failure.
        _execute(conn, "CREATE TEMP TABLE sentiment_stage AS SELECT * FROM sentiment_predictions WHERE 1=0")
        eligibility = "" if rescore_existing else """AND NOT EXISTS (
            SELECT 1 FROM sentiment_predictions sp WHERE sp.id = preprocessed.id
              AND sp.content_type = preprocessed.content_type)"""
        cursor = _execute(conn, f"""SELECT id, content_type, clean_text FROM preprocessed
            WHERE is_filtered = {_false(conn)} AND clean_text IS NOT NULL
              AND clean_text != '' {eligibility}""")
        marker = _marker(conn)
        columns = "id, content_type, label, confidence, logits, model_version"
        while batch := cursor.fetchmany(batch_size):
            preds = predict_batch([r["clean_text"] for r in batch], model_dir,
                                  batch_size=min(64, batch_size), device=device, runtime=runtime)
            if len(preds) != len(batch):
                raise ValueError("Prediction count does not match input batch")
            rows = []
            for record, pred in zip(batch, preds):
                logits = json.dumps(pred["logits"])
                rows.append((record["id"], record["content_type"], pred["label"],
                             pred["confidence"], _json_value(logits) if is_postgres_connection(conn) else logits,
                             model_version))
                positive += pred["label"] == "positive"
                negative += pred["label"] == "negative"
                neutral += pred["label"] == "neutral"
            _executemany(conn, f"INSERT INTO sentiment_stage ({columns}) VALUES ({', '.join([marker] * 6)})", rows)
            total += len(rows)
        if model_fingerprint(model_dir) != model_version:
            raise ValueError("Model artifacts changed during inference; refusing promotion")
        if rescore_existing:
            _execute(conn, "DELETE FROM sentiment_predictions")
        _execute(conn, f"INSERT INTO sentiment_predictions ({columns}) SELECT {columns} FROM sentiment_stage")
        _execute(conn, """CREATE TABLE IF NOT EXISTS sentiment_model_active (
            slot INTEGER PRIMARY KEY, model_dir TEXT NOT NULL, model_version TEXT NOT NULL
        )""")
        _execute(conn, f"""INSERT INTO sentiment_model_active (slot, model_dir, model_version)
            VALUES (1, {marker}, {marker}) ON CONFLICT (slot) DO UPDATE SET
            model_dir = excluded.model_dir, model_version = excluded.model_version""",
            (str(Path(model_dir).resolve()), model_version))
        if promote_candidate:
            consumed = _execute(conn, f"""DELETE FROM sentiment_model_candidate
                WHERE slot = 1 AND model_dir = {marker}""", (str(Path(model_dir).resolve()),))
            if consumed.rowcount != 1:
                raise ValueError("The trained candidate changed before publication")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
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
