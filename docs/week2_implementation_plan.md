# Week 2 Implementation Plan — Sentiment Model

## Context

Week 1 is complete: the `preprocessed` SQLite table is populated, sentence embeddings are cached at `models/embeddings_cache.npy`, and `scripts/generate_weak_labels.py` produces a high-confidence labeled CSV.

Week 2 builds the sentiment classification layer: fine-tune `distilbert-base-uncased` on the weak labels, run batch inference across all preprocessed records, and store predictions back to SQLite. The gate is macro F1 ≥ 0.70 on a held-out validation split.

---

## Deliverables

- [x] `scripts/generate_weak_labels.py` — Add `--include-neutral` flag for 3-class labeling
- [x] `src/ml/db.py` — Add `ensure_sentiment_table`, `iter_unscored_records`, `upsert_sentiment`
- [x] `src/ml/sentiment.py` — DistilBERT fine-tuning pipeline + inference
- [x] `src/ml/__init__.py` — Export new public API from sentiment.py
- [x] `scripts/batch_inference.py` — CLI: load model, batch-predict all unscored records, write to DB
- [x] `tests/test_sentiment.py` — 9 unit + integration tests (all passing)

---

## Apple Silicon / MPS Notes

DistilBERT training on MPS:
- Set `use_mps_device=True` in `TrainingArguments` (transformers 4.21+)
- `PYTORCH_ENABLE_MPS_FALLBACK=1` must be in `.env`
- `per_device_train_batch_size=16` on MPS
- Do not use `fp16=True` on MPS — keep float32

Inference on MPS:
- Reuses `_detect_device()` from `src/ml/preprocessing.py` pattern (mps → cuda → cpu)
- `model.to(device)` + tokenizer tensors `.to(device)`

---

## Database Change

Added `sentiment_predictions` table to `reddit_data.db` (migration via `CREATE TABLE IF NOT EXISTS`):

```
sentiment_predictions
  id            TEXT PRIMARY KEY   -- same ID as preprocessed.id
  content_type  TEXT               -- 'post' or 'comment'
  label         TEXT               -- 'positive', 'neutral', 'negative'
  confidence    REAL               -- softmax max probability
  logits        TEXT               -- JSON array [neg_score, neu_score, pos_score]
  model_version TEXT               -- model dir path tag
  predicted_at  DATETIME
```

---

## Implementation Detail

### `scripts/generate_weak_labels.py` (edited)
Added `--include-neutral` (default `False`) and `--neutral-threshold` (default `0.1`).

When `--include-neutral` is set:
- compound > threshold → `positive`
- compound < -threshold → `negative`
- |compound| < neutral_threshold → `neutral` (sampled to match minority class size)
- Rows between thresholds are discarded (ambiguous)

### `src/ml/db.py` (edited — 3 new functions)
- `ensure_sentiment_table(conn)` — `CREATE TABLE IF NOT EXISTS sentiment_predictions ...`
- `iter_unscored_records(conn, batch_size=1000)` — yields batches from `preprocessed` where `is_filtered=0` and `id NOT IN (SELECT id FROM sentiment_predictions)`
- `upsert_sentiment(conn, rows)` — batch `INSERT OR REPLACE`; rows are `(id, content_type, label, confidence, logits_json, model_version)`

### `src/ml/sentiment.py` (created)
Label map: `{negative:0, neutral:1, positive:2}`

**`train(weak_labels_path, model_dir, val_split=0.2, epochs=3, lr=2e-5, batch_size=16, ...)`**
1. Load CSV; stratified 80/20 split by label
2. Tokenize with `DistilBertTokenizerFast` (max_length=256)
3. Build `DistilBertForSequenceClassification(num_labels=3)`
4. Detect device (mps → cuda → cpu); set `use_mps_device=True` when on MPS
5. Train with HuggingFace `Trainer`; save best checkpoint by macro F1
6. Log to MLflow run `week2-sentiment-train`

**`predict_batch(texts, model_dir, batch_size=64, device=None) -> list[dict]`**
- Lazy-loads tokenizer + model; runs inference in chunks
- Returns `{label, confidence, logits}` per text

**`run_batch_inference(db_path, model_dir, batch_size=1000, ...) -> dict`**
- Iterates `iter_unscored_records`, calls `predict_batch`, writes `upsert_sentiment`
- Logs to MLflow run `week2-batch-inference`

### `scripts/batch_inference.py` (created)
CLI: `python scripts/batch_inference.py --db reddit_data.db --model-dir models/sentiment_v1`

---

## File Map (Critical Paths)

| Path | Action | Notes |
|------|--------|-------|
| `scripts/generate_weak_labels.py` | Edit | `--include-neutral`, `--neutral-threshold` flags added |
| `src/ml/db.py` | Edit | 3 new sentiment DB helpers |
| `src/ml/sentiment.py` | Create | Full fine-tuning + inference module |
| `src/ml/__init__.py` | Edit | Exports `train`, `predict_batch`, `run_batch_inference`, label maps |
| `scripts/batch_inference.py` | Create | CLI orchestrator |
| `tests/test_sentiment.py` | Create | 9 tests, all passing |

---

## Tests

`tests/test_sentiment.py` (9 tests, all passing):
- `test_label2id_keys` — assert positive/neutral/negative all present
- `test_label2id_values_unique` — no duplicate int values
- `test_id2label_inverse` — round-trip check
- `test_predict_batch_output_length` — mocked model, correct output count
- `test_predict_batch_confidence_in_range` — confidence in [0, 1]
- `test_predict_batch_label_valid` — labels are one of positive/neutral/negative
- `test_predict_batch_logits_length` — logits list has 3 elements
- `test_run_batch_inference_integration` — temp DB, mocked predict_batch, asserts `sentiment_predictions` has 3 rows (filtered record excluded)
- `test_run_batch_inference_idempotent` — second run adds 0 rows

---

## Verification (Gate Checks)

```bash
# 1. Generate 3-class weak labels (include neutral)
python scripts/generate_weak_labels.py \
  --db reddit_data.db \
  --output data/weak_labels.csv \
  --threshold 0.5 \
  --include-neutral \
  --neutral-threshold 0.1

# 2. Check label distribution
python -c "import pandas as pd; df=pd.read_csv('data/weak_labels.csv'); print(df.label.value_counts())"

# 3. Fine-tune DistilBERT (will use MPS automatically)
python -c "
from src.ml.sentiment import train
result = train('data/weak_labels.csv', 'models/sentiment_v1')
print('val_f1:', result['val_f1'])
"

# 4. Gate: val_f1_macro >= 0.70
# If below threshold, lower --threshold to 0.4 and regenerate labels, then retrain

# 5. Run batch inference on all records
python scripts/batch_inference.py --db reddit_data.db --model-dir models/sentiment_v1

# 6. Verify predictions in DB
python -c "
import sqlite3; conn=sqlite3.connect('reddit_data.db')
rows=conn.execute('SELECT label, COUNT(*) FROM sentiment_predictions GROUP BY label').fetchall()
print(rows)
"

# 7. Run tests
pytest tests/test_sentiment.py tests/test_preprocessing.py -v

# 8. Check MLflow
mlflow ui --backend-store-uri mlruns/
```

Gate passes when: `val_f1_macro ≥ 0.70` AND `sentiment_predictions` table populated for all `is_filtered=0` records AND all tests pass.
