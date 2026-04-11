# Reddit Analyzer — Product Requirements Document

**Version:** 2.0
**Status:** Phase 1 complete. Phase 2 Weeks 1–2 complete. Week 3 (Topic Modeling) in progress.
**Last Updated:** April 2026

---

## 1. Project Summary

A local, batch-processing system that collects Reddit discussions about AI and technology, runs sentiment analysis and topic modeling on them, and surfaces trends through an interactive dashboard. The system is fully offline — no cloud infrastructure required during normal operation.

**What's already built (Phase 1):** A production-quality Reddit data collection pipeline. It pulls posts and comments from configurable subreddits, stores everything in SQLite, respects Reddit's API rate limits via a circuit breaker + exponential backoff pattern, and supports both real-time and historical collection. The database currently holds 227MB of collected data.

**What needs to be built (Phase 2):** The entire ML and visualization layer — preprocessing, sentiment classification, topic modeling, time series analysis, a Streamlit dashboard, and scheduled automation of the full pipeline.

---

## 2. Target Audience & Use Case

Personal research and analysis tool. The operator runs collection on a schedule and opens the dashboard on demand to explore trends — which AI topics are gaining/losing sentiment, which subreddits are most active, how discussion patterns shift over time.

---

## 3. Data Configuration (Current State)

**Subreddits being collected:**
`r/technology`, `r/artificial`, `r/chatgpt`, `r/openai`, `r/MachineLearning`

**Keywords being tracked:**
`AI`, `claude`, `chatgpt`, `transformer`, `RAG`, `MCP`

These can be expanded via `.env` at any time. The original economics-focused subreddits (`r/Economics`, `r/investing`, `r/personalfinance`) remain an optional future extension.

---

## 4. Phase 2 Scope

### 4.1 Preprocessing Pipeline

Clean and normalize raw text from the SQLite database before feeding it to ML models.

- Strip URLs, markdown syntax, Reddit quote formatting, excessive whitespace
- Filter bot accounts and very short posts (< 10 tokens)
- Normalize to lowercase; optionally lemmatize with spaCy
- Generate sentence embeddings using `all-MiniLM-L6-v2` (22M params, fast)
- Cache embeddings on disk to avoid recomputation on subsequent runs

**Output:** A `preprocessed` table in SQLite, plus a flat embedding cache file.

---

### 4.2 Sentiment Analysis

Classify each post and comment as Positive, Neutral, or Negative with a confidence score.

**Approach — two phases:**

Phase 1 (weak supervision): Use VADER scores as automatic labels. Only keep high-confidence labels (|score| > 0.5). This generates ~50k labeled examples for free.

Phase 2 (fine-tuning): Fine-tune `distilbert-base-uncased` on the weakly labeled dataset for 3 epochs. Architecture: DistilBERT encoder → Dropout(0.1) → Linear(768→3) → Softmax. Target F1 > 0.70 on a held-out validation set.

**Inference:** Batch mode — process all new posts since the last run in batches of 1,000. Store predictions (label + confidence score) back into SQLite.

---

### 4.3 Topic Modeling

Discover and track the dominant themes in collected discussions.

**Model:** BERTopic with the following configuration:
- Embeddings: `all-MiniLM-L6-v2` (shared with preprocessing)
- Dimensionality reduction: UMAP
- Clustering: HDBSCAN with min topic size 30
- Representation: c-TF-IDF, max 50–100 topics

**Temporal tracking:** Run topic modeling weekly on a rolling window to detect emerging topics (new clusters), declining topics (shrinking clusters), and topic sentiment over time.

**Output:** Topic assignments and keyword lists stored in SQLite; topic-over-time data exported for dashboard visualization.

---

### 4.4 Time Series Analysis

Aggregate daily sentiment scores and identify trends.

- Daily and 7/30-day moving average sentiment per subreddit
- Change point detection using the PELT algorithm
- 7–14 day sentiment forecast using Facebook Prophet
- Topic-specific sentiment trend tracking

---

### 4.5 Streamlit Dashboard

An on-demand local dashboard (`streamlit run app.py`) with five tabs:

**Overview** — Key metrics (posts collected, current sentiment ratio, top trending topics, last collection timestamp)

**Sentiment Trends** — Time series chart with date range selector, moving average overlays, subreddit comparison, change point annotations, and Prophet forecast with confidence bands

**Topic Explorer** — Topic list with keywords and document counts, topic-over-time heatmap, word clouds per topic, emerging topics highlight (new in last 7 days)

**Deep Dive** — Search posts by keyword/subreddit/date, view individual posts with their predictions and confidence scores, export filtered results as CSV

**Model Health** — Prediction confidence distribution, VADER vs. model agreement chart, drift metrics, last retrain date

---

### 4.6 Automated Pipeline

Extend the existing collection schedule to run the full ML pipeline daily:

```
02:00 AM  — Collect new Reddit data (existing)
02:30 AM  — Preprocess new records
03:00 AM  — Run batch sentiment inference
03:30 AM  — Update topic model (incremental)
04:00 AM  — Compute time series aggregations
04:30 AM  — Drift check; alert if confidence drops below threshold
```

All steps log to the existing `logs/` directory. Alerts can be email or Slack (configured via `.env`).

---

### 4.7 Drift Detection & Model Health

Weekly automated checks:

- KS test comparing current week's embeddings vs. baseline
- Chi-square test on sentiment distribution shifts
- Alert if prediction confidence average drops below 0.75
- Alert if VADER agreement drops significantly (suggests concept drift)

If drift is detected: generate a report to `logs/drift_report_YYYY-MM-DD.html` and trigger a retrain flag. Monthly scheduled retrain regardless of drift.

MLflow used locally for experiment tracking — all training runs, hyperparameters, and metrics logged. No remote server needed.

---

## 5. Repository Structure (Target State)

```
reddit-analyzer/
├── app.py                        # Streamlit dashboard entry point
├── src/
│   ├── reddit_api/               # ✅ COMPLETE — data collection
│   └── ml/                       # 🔲 TO BUILD
│       ├── preprocessing.py      # Text cleaning + embedding generation
│       ├── sentiment.py          # DistilBERT training + batch inference
│       ├── topics.py             # BERTopic training + temporal tracking
│       └── timeseries.py         # Aggregation, change points, Prophet
├── scripts/
│   ├── collect-historical.py     # ✅ COMPLETE
│   ├── batch_inference.py        # 🔲 TO BUILD
│   ├── train_models.py           # 🔲 TO BUILD
│   ├── detect_drift.py           # 🔲 TO BUILD
│   └── notify.py                 # 🔲 TO BUILD
├── models/                       # 🔲 TO CREATE — trained model artifacts
├── notebooks/                    # Exploration notebooks
├── tests/                        # ✅ Partial — collection tests exist
├── docs/
└── pyproject.toml                # ✅ COMPLETE (ml + production deps declared)
```

---

## 6. Implementation Plan

### Week 1 — Preprocessing & Weak Labels
- [x] `src/ml/preprocessing.py` — text cleaner + embedding generator
- [x] VADER weak labeling script → generate labeled training CSV
- [x] EDA notebook on current 227MB database
- [x] Configure MLflow locally

**Gate:** Labeled dataset ≥ 30k examples, embedding cache working.

---

### Week 2 — Sentiment Model
- [x] `src/ml/sentiment.py` — DistilBERT fine-tuning pipeline
- [x] Train on weak labels; evaluate on 500 manual validation examples
- [x] `scripts/batch_inference.py` — process all existing DB records
- [x] Log run to MLflow

**Gate:** Validation F1 ≥ 0.70.

---

### Week 3 — Topic Modeling
- [ ] `src/ml/topics.py` — BERTopic with sentence-transformers
- [ ] Train on 90-day historical slice
- [ ] Temporal topic tracking (weekly slices)
- [ ] Export topic keywords and assignments to SQLite

**Gate:** ≥ 20 coherent topics; topic coherence score ≥ 0.50.

---

### Week 4 — Time Series & Forecasting
- [ ] `src/ml/timeseries.py` — daily aggregation + PELT + Prophet
- [ ] Topic-specific sentiment trends
- [ ] Validation notebooks

**Gate:** Prophet generating 7-day forecasts with reasonable confidence intervals.

---

### Week 5 — Dashboard
- [ ] `app.py` — Streamlit app with all 5 tabs
- [ ] Connect all tabs to live SQLite data
- [ ] Export functionality (CSV/JSON)

**Gate:** Dashboard launches cleanly, all charts render from real data.

---

### Week 6 — Automation, Drift & Polish
- [ ] Extend cron pipeline to include ML steps
- [ ] `scripts/detect_drift.py` with weekly report generation
- [ ] `scripts/notify.py` for email/Slack alerts
- [ ] Expand test coverage to ML modules
- [ ] Final documentation pass

**Gate:** Full pipeline runs unattended for 3 days without errors.

---

## 7. Success Criteria

| Metric | Target |
|---|---|
| Sentiment model F1 | ≥ 0.70 |
| Topic coherence | ≥ 0.50 |
| Daily pipeline runtime | < 30 minutes |
| Dashboard load time | < 5 seconds |
| Drift false positive rate | < 5% |
| Pipeline uptime | ≥ 99% |

---

## 8. Out of Scope (for Now)

- Docker / containerization
- Cloud deployment (AWS, GCP, Streamlit Cloud)
- PostgreSQL migration
- Real-time streaming / websockets
- REST API / FastAPI serving layer
- Multi-language support
- Economics subreddit integration (can be enabled via `.env` at any time)
