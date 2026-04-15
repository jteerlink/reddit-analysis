# Execution Guide — Weeks 1–4

Step-by-step commands to run the full ML pipeline from raw Reddit data through time series forecasting.

---

## Prerequisites

```bash
# Install all dependencies (ml + production extras)
uv pip install -e ".[ml,production]"

# Confirm the database exists
ls -lh historical_reddit_data.db

# Create the models and data directories
mkdir -p models/ data/
```

All commands assume you are running from the project root with the virtual environment active.

---

## Week 1 — Preprocessing & Weak Labels

**Goal:** Clean raw posts/comments, generate sentence embeddings, and produce a labeled training CSV.

### Step 1 — Run preprocessing

```bash
python - <<'EOF'
from src.ml.preprocessing import run_preprocessing

result = run_preprocessing(
    db_path="historical_reddit_data.db",
    cache_dir="models/",
    batch_size=1000,
    embed_batch_size=256,   # 256 optimal for MPS
    mlflow_tracking=True,
)

print(f"Total records:   {result['total']:,}")
print(f"Filtered:        {result['filtered']:,}")
print(f"Kept:            {result['kept']:,}")
print(f"Device:          {result['device']}")
EOF
```

This writes all kept records to the `preprocessed` table and saves the embedding cache to `models/embeddings.npy` + `models/embedding_index.json`.

**Gate:** Embedding cache file must exist at `models/embeddings.npy`.

### Step 2 — Generate weak labels

```bash
python scripts/generate_weak_labels.py \
    --db historical_reddit_data.db \
    --output data/weak_labels.csv \
    --threshold 0.5 \
    --include-neutral \
    --neutral-threshold 0.1
```

Expected output:
```
Total scored:    227,000+
Kept:            50,000+
  Positive:      ~40%
  Negative:      ~40%
  Neutral:       ~20%
Output:          data/weak_labels.csv
Gate (≥30k):     PASS ✓
```

**Gate:** `data/weak_labels.csv` must contain ≥ 30,000 labeled rows.

### Validation

```bash
# Confirm preprocessed row count
python -c "
import sqlite3
conn = sqlite3.connect('historical_reddit_data.db')
n = conn.execute('SELECT COUNT(*) FROM preprocessed WHERE is_filtered=0').fetchone()[0]
print(f'Preprocessed (kept): {n:,}')
"

# Confirm embedding cache
python -c "
import numpy as np, json
arr = np.load('models/embeddings_cache.npy')
idx = json.load(open('models/embeddings_index.json'))
print(f'Embeddings shape: {arr.shape}  |  Index entries: {len(idx)}')
"

# Confirm weak labels
python -c "
import pandas as pd
df = pd.read_csv('data/weak_labels.csv')
print(df['label'].value_counts())
print(f'Total: {len(df):,}')
"
```

### MLflow

```bash
mlflow ui --port 5001
# Open http://localhost:5001 → Experiment "reddit-analyzer-phase2" → run "week1-preprocessing"
```

---

## Week 2 — Sentiment Model

**Goal:** Fine-tune DistilBERT on weak labels, then score all preprocessed records.

### Step 1 — Train the sentiment model

```bash
python - <<'EOF'
from src.ml.sentiment import train
import re

result = train(
    weak_labels_path="data/weak_labels.csv",
    model_dir="models/sentiment_v1",
    val_split=0.2,
    epochs=3,
    lr=2e-5,
    batch_size=16,        # reduce to 8 if OOM
    max_length=256,
    mlflow_tracking=True,
)

print(f"Val F1 (macro):  {result['val_f1']:.4f}")
print(f"  F1 positive:   {result['f1_positive']:.4f}")
print(f"  F1 neutral:    {result['f1_neutral']:.4f}")
print(f"  F1 negative:   {result['f1_negative']:.4f}")
print(f"Device:          {result['device']}")
print(f"Model saved to:  {result['model_dir']}")
EOF
```

Training time: ~20–40 min on MPS (M-series Mac), longer on CPU.

**Gate:** Validation F1 ≥ 0.70. If the gate fails, try `--threshold 0.4` in Step 2 of Week 1 to get a larger/cleaner training set.

### Step 2 — Run batch inference on all records

```bash
python scripts/batch_inference.py \
    --db historical_reddit_data.db \
    --model-dir models/sentiment_v1 \
    --batch-size 1000
```

Expected output:
```
Inference complete
Total scored:  200,000+
  Positive:    ~45%
  Neutral:     ~35%
  Negative:    ~20%
Model:         models/sentiment_v1
Device:        mps
```

### Validation

```bash
# Check prediction counts and class distribution
python -c "
import sqlite3
conn = sqlite3.connect('historical_reddit_data.db')
rows = conn.execute('''
    SELECT label, COUNT(*) AS n
    FROM sentiment_predictions
    GROUP BY label
    ORDER BY label
''').fetchall()
total = sum(r[1] for r in rows)
for label, n in rows:
    print(f'  {label:<10} {n:>8,}  ({100*n/total:.1f}%)')
print(f'  {\"Total\":<10} {total:>8,}')
"

# Spot-check a few predictions
python -c "
import sqlite3
conn = sqlite3.connect('historical_reddit_data.db')
rows = conn.execute('''
    SELECT sp.label, sp.confidence, p.clean_text
    FROM sentiment_predictions sp
    JOIN preprocessed p ON sp.id = p.id
    ORDER BY RANDOM()
    LIMIT 5
''').fetchall()
for label, conf, text in rows:
    print(f'[{label} {conf:.2f}] {text[:120]}')
"
```

### MLflow

```bash
mlflow ui --port 5001
# Experiment "reddit-analyzer-phase2" → run "week2-sentiment-training"
# Check: val_f1, f1_positive, f1_neutral, f1_negative, epochs, lr
```

---

## Week 3 — Topic Modeling

**Goal:** Discover dominant themes in Reddit discussions and track them weekly.

### Step 1 — Train BERTopic

```bash
python scripts/train_topic_model.py \
    --db historical_reddit_data.db \
    --cache-dir models/ \
    --days 90 \
    --min-cluster-size 30 \
    --min-topic-size 30 \
    --nr-topics auto
```

Expected output:
```
==================================================
Topic Modeling Complete
Total documents:    180,000+
Topics discovered:  40–80   (excluding outliers)
Outlier documents:  20,000+  (10–15%)
Coherent topics:    25+  (coherence >= 0.50)
Mean coherence:     0.55+
Gate:               PASSED (>= 20 coherent topics required)
Device:             mps
Window:             90 days
==================================================
```

**Gate:** ≥ 20 coherent topics with mean coherence ≥ 0.50.

If the gate fails:
- Lower `--min-cluster-size` to 15 and retry
- Add `--skip-gate` to write results anyway and inspect topics manually

### Validation

```bash
# Top topics by document count
python -c "
import sqlite3, json
conn = sqlite3.connect('historical_reddit_data.db')
rows = conn.execute('''
    SELECT topic_id, keywords, doc_count, coherence_score
    FROM topics
    ORDER BY doc_count DESC
    LIMIT 15
''').fetchall()
for tid, kw, cnt, coh in rows:
    kws = ', '.join(json.loads(kw)[:5])
    print(f'Topic {tid:3d}  docs={cnt:6,}  coh={coh:.3f}  [{kws}]')
"

# Temporal coverage
python -c "
import sqlite3
conn = sqlite3.connect('historical_reddit_data.db')
rows = conn.execute('''
    SELECT week_start, COUNT(DISTINCT topic_id) AS topics, SUM(doc_count) AS docs
    FROM topic_over_time
    GROUP BY week_start
    ORDER BY week_start DESC
    LIMIT 8
''').fetchall()
print(f'{\"Week\":<12} {\"Topics\":>8} {\"Docs\":>10}')
for week, topics, docs in rows:
    print(f'{week:<12} {topics:>8} {docs:>10,}')
"
```

### MLflow

```bash
mlflow ui --port 5001
# Experiment "reddit-analyzer-phase2" → run "week3-topic-modeling"
# Check: n_topics, coherent_topic_count, mean_coherence, outlier_ratio
```

---

## Week 4 — Time Series & Forecasting

**Goal:** Aggregate daily sentiment, detect trend shifts, generate Prophet forecasts, and compute topic-level trends.

### Step 1 — Run time series analysis

```bash
python scripts/run_timeseries.py \
    --db historical_reddit_data.db \
    --days 90 \
    --forecast-days 14
```

Expected output:
```
==================================================
Time Series Analysis Complete
Daily sentiment rows:    450+   (5 subreddits × ~90 days)
Moving average rows:     450+
Change points detected:  10–30
Forecast rows:           70    (5 subreddits × 14 days)
Topic trend rows:        3,000+
Gate:                    PASSED (forecast generated)
Window:                  90 days
Forecast horizon:        14 days
==================================================
```

**Gate:** Forecast rows must be non-zero (Prophet successfully fit and projected).

If the gate fails, the most common cause is too few data points per subreddit (< 7 days). Run `batch_inference.py` first to ensure sentiment predictions exist.

### Validation

```bash
# Confirm all 5 tables populated
python -c "
import sqlite3
conn = sqlite3.connect('historical_reddit_data.db')
for table in ['sentiment_daily', 'sentiment_moving_avg', 'change_points', 'sentiment_forecast', 'topic_sentiment_trends']:
    n = conn.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
    print(f'  {table:<30} {n:>8,} rows')
"

# Preview forecast for one subreddit
python -c "
import sqlite3
conn = sqlite3.connect('historical_reddit_data.db')
rows = conn.execute('''
    SELECT subreddit, date, yhat, yhat_lower, yhat_upper
    FROM sentiment_forecast
    ORDER BY subreddit, date
    LIMIT 14
''').fetchall()
print(f'{\"Subreddit\":<20} {\"Date\":<12} {\"yhat\":>7} {\"lower\":>7} {\"upper\":>7}')
for r in rows:
    print(f'{r[0]:<20} {r[1]:<12} {r[2]:>7.3f} {r[3]:>7.3f} {r[4]:>7.3f}')
"
```

### Validation notebook

```bash
jupyter notebook notebooks/timeseries_validation.ipynb
```

The notebook renders four charts:
1. Daily sentiment + 7/30-day moving averages per subreddit
2. PELT change points overlaid on the sentiment series
3. Prophet forecast with 95% confidence bands
4. Topic sentiment heatmap (topic × time)

### MLflow

```bash
mlflow ui --port 5001
# Experiment "reddit-analyzer-phase2" → run "timeseries_analysis"
# Check: daily_rows, change_point_rows, forecast_rows, topic_trend_rows
```

---

## Full Pipeline (Weeks 1–4 in sequence)

```bash
# 1. Preprocess
python - <<'EOF'
from src.ml.preprocessing import run_preprocessing
run_preprocessing("historical_reddit_data.db", cache_dir="models/")
EOF

# 2. Generate weak labels
python scripts/generate_weak_labels.py \
    --db historical_reddit_data.db \
    --output data/weak_labels.csv \
    --threshold 0.5 \
    --include-neutral

# 3. Train sentiment model
python - <<'EOF'
from src.ml.sentiment import train
train("data/weak_labels.csv", model_dir="models/sentiment_v1")
EOF

# 4. Batch inference
python scripts/batch_inference.py \
    --db historical_reddit_data.db \
    --model-dir models/sentiment_v1

# 5. Topic modeling
python scripts/train_topic_model.py \
    --db historical_reddit_data.db \
    --cache-dir models/ \
    --days 90

# 6. Time series
python scripts/run_timeseries.py \
    --db historical_reddit_data.db \
    --days 90 \
    --forecast-days 14
```

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `ModuleNotFoundError: ruptures` | Missing ML deps | `uv pip install -e ".[ml]"` |
| `ModuleNotFoundError: prophet` | Missing ML deps | `uv pip install -e ".[ml]"` |
| Forecast gate fails | Fewer than 7 daily data points per subreddit | Run `batch_inference.py` to populate `sentiment_predictions` first |
| Coherence gate fails | Embeddings don't cover the full 90-day window | Lower `--min-cluster-size` or widen `--days` |
| MPS out of memory | Batch too large | Reduce `--batch-size` to 8 for training, 512 for inference |
| `database not found` | Wrong working directory | Run commands from project root |
