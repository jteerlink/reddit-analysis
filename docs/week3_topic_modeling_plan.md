# Week 3 — BERTopic Topic Modeling

## Context

Phase 2 Week 3 of the PRD. Weeks 1 (preprocessing) and 2 (sentiment/DistilBERT) are complete. This week adds topic modeling: BERTopic trained on a 90-day rolling window of preprocessed Reddit posts/comments, with temporal tracking and SQLite output. Gate: ≥20 coherent topics, mean coherence ≥0.50.

---

## Files to Create / Modify

| Action | File |
|--------|------|
| Modify | `src/ml/db.py` |
| Create | `src/ml/topics.py` |
| Create | `scripts/train_topic_model.py` |
| Create | `tests/test_topics.py` |
| Modify | `pyproject.toml` |

---

## 1. `pyproject.toml` — Add to `[ml]` optional group

Add two lines to the `ml` extras list:
- `"bertopic>=0.15.0"`
- `"hdbscan>=0.8.33"`

(`umap-learn>=0.5.0` is already declared.)

---

## 2. `src/ml/db.py` — 5 New Functions

Append to the end of the file following the exact style of existing functions.

### New tables: `ensure_topics_tables(conn)`

Three tables in one function call + commit:

```
topics (
    topic_id        INTEGER PRIMARY KEY,
    keywords        TEXT NOT NULL,        -- JSON array of strings
    doc_count       INTEGER NOT NULL DEFAULT 0,
    coherence_score REAL,                 -- NULL for topic -1
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
)
INDEX: idx_topics_coherence ON topics(coherence_score)

topic_assignments (
    id          TEXT PRIMARY KEY,         -- FK to preprocessed.id
    topic_id    INTEGER NOT NULL,
    probability REAL,
    assigned_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (id) REFERENCES preprocessed(id)
)
INDEX: idx_topic_assignments_topic ON topic_assignments(topic_id)

topic_over_time (
    topic_id      INTEGER NOT NULL,
    week_start    TEXT NOT NULL,          -- ISO date, always a Monday
    doc_count     INTEGER NOT NULL DEFAULT 0,
    avg_sentiment REAL,
    PRIMARY KEY (topic_id, week_start)
)
INDEX: idx_tot_week ON topic_over_time(week_start)
```

### `iter_preprocessed_for_topics(conn, days=90, batch_size=1000)`

Generator yielding batches. Filters: `is_filtered=0`, non-null `clean_text` and `embedding_key`, `processed_at >= datetime('now', '-N days')`. Must JOIN back to `posts`/`comments` to get `source_timestamp` (original Reddit post time, needed for weekly bucketing):

```sql
SELECT p.id, p.content_type, p.clean_text, p.embedding_key,
       COALESCE(posts.timestamp, comments.timestamp) AS source_timestamp
FROM preprocessed p
LEFT JOIN posts ON p.id = posts.id AND p.content_type = 'post'
LEFT JOIN comments ON p.id = comments.id AND p.content_type = 'comment'
WHERE p.is_filtered = 0
  AND p.clean_text IS NOT NULL AND p.clean_text != ''
  AND p.embedding_key IS NOT NULL
  AND p.processed_at >= datetime('now', :cutoff)
```

### `upsert_topics(conn, rows)` — `INSERT OR REPLACE`, tuple: `(topic_id, keywords_json, doc_count, coherence_score)`

### `upsert_topic_assignments(conn, rows)` — `INSERT OR REPLACE`, tuple: `(id, topic_id, probability)`

### `upsert_topic_over_time(conn, rows)` — `INSERT OR REPLACE`, tuple: `(topic_id, week_start, doc_count, avg_sentiment)`

---

## 3. `src/ml/topics.py` — New Module

Follow `preprocessing.py` / `sentiment.py` structure exactly: constants → helper class → model class → orchestrator function.

### Constants

```python
OUTLIER_TOPIC_ID = -1
MIN_TOPIC_COUNT_GATE = 20
MIN_COHERENCE_GATE = 0.50
EMBEDDING_DIM = 384
SENTIMENT_SCORE_MAP = {"positive": 1.0, "neutral": 0.0, "negative": -1.0}
```

### `_detect_device()` — copy from `preprocessing.py` (MPS→CUDA→CPU)

### Class `EmbeddingCache(cache_dir="models/")`

Read-only wrapper around the numpy cache produced by Week 1 preprocessing.

- `load() -> (np.ndarray, Dict[str, int])` — reads `models/embeddings_cache.npy` + `models/embeddings_index.json` lazily; raises `FileNotFoundError` if missing
- `get_subset(embedding_keys: List[str]) -> np.ndarray` — uses numpy fancy indexing (`arr[row_indices]`) to extract subset without copying full array; skips missing keys with a warning; returns shape `(len(valid_keys), 384)`

### Class `TopicModeler`

`__init__(cache_dir, n_neighbors=15, n_components=5, min_cluster_size=30, nr_topics="auto", min_topic_size=30)`

**`_build_model() -> BERTopic`** — constructs pipeline:
```
UMAP(n_neighbors, n_components, min_dist=0.0, metric="cosine", random_state=42)
HDBSCAN(min_cluster_size, metric="euclidean", cluster_selection_method="eom", prediction_data=True)
BERTopic(umap_model, hdbscan_model, nr_topics, min_topic_size, calculate_probabilities=True, verbose=False)
```

**`train(docs, embeddings) -> (List[int], np.ndarray)`** — calls `self._model.fit_transform(docs, embeddings)`; returns `(topic_ids, probs)`

**`get_topic_info() -> List[Dict]`** — wraps `self._model.get_topic_info()` DataFrame; returns list of `{topic_id, keywords (list[str]), doc_count}` for all topics including -1; gets keywords via `self._model.get_topic(topic_id)` (list of `(word, score)` tuples → extract words only)

**`compute_coherence(topic_id, docs) -> float`** — UMass coherence (no gensim needed):
1. Get top-10 keywords for topic via `self._model.get_topic(topic_id)`
2. Get docs assigned to this topic
3. For each keyword pair `(w_i, w_j)`: count docs containing both (`D(w_i,w_j)`) and docs containing `w_j` (`D(w_j)`)
4. Score = `mean(log((D(w_i,w_j)+1) / (D(w_j)+1)))` over all pairs
5. Normalize to [0,1] by dividing by `log(len(docs)+1)`

**`check_gate(coherence_scores: List[float]) -> (bool, Dict)`** — counts scores ≥ `MIN_COHERENCE_GATE`; passes if count ≥ `MIN_TOPIC_COUNT_GATE`; returns `(passed, {n_coherent_topics, mean_coherence, ...})`

### `run_topic_modeling(db_path, cache_dir="models/", days=90, batch_size=1000, n_neighbors=15, n_components=5, min_cluster_size=30, nr_topics="auto", min_topic_size=30, mlflow_tracking=True, skip_gate_check=False) -> Dict`

**Flow:**
1. Start MLflow run, log all hyperparams + device
2. Open DB, call `ensure_topics_tables(conn)`
3. Accumulate ALL records from `iter_preprocessed_for_topics()` into memory (lists of ids, docs, embedding_keys, source_timestamps, content_types) — BERTopic requires full corpus for `fit_transform`
4. `EmbeddingCache.get_subset(all_embedding_keys)` → shape `(N, 384)` array
5. `modeler._build_model()` then `modeler.train(all_docs, embeddings)` → `(topic_assignments, probs)`
6. `modeler.get_topic_info()` → topic list; for each `topic_id != -1`, `modeler.compute_coherence(topic_id, all_docs)` → `coherence_by_id`
7. `modeler.check_gate(list(coherence_by_id.values()))` → log to MLflow
8. **Clear old results:** `DELETE FROM topics; DELETE FROM topic_assignments; DELETE FROM topic_over_time; commit`
9. `upsert_topics()` — include topic -1 with `keywords='[]'` and `coherence_score=None`
10. `upsert_topic_assignments()` — all docs including outliers; batch by `batch_size`
11. **Temporal tracking:** bucket docs by ISO week using `source_timestamp`; skip docs with null timestamp; for each `(topic_id, week_start)` pair where `topic_id != -1` and `doc_count > 0`, query `sentiment_predictions` via `WHERE id IN (...)`, map labels to `SENTIMENT_SCORE_MAP`, compute per-topic avg; `upsert_topic_over_time()`
12. Log metrics: `n_topics`, `n_outliers`, `total_docs`, `coherent_topic_count`, `mean_coherence`; end MLflow run
13. Return summary dict

---

## 4. `scripts/train_topic_model.py`

CLI with argparse (`--db`, `--cache-dir`, `--days`, `--batch-size`, `--nr-topics`, `--min-cluster-size`, `--skip-gate`, `--no-mlflow`). Calls `run_topic_modeling()`. Prints formatted summary block. Exits with code 1 if gate fails and `--skip-gate` not set.

---

## 5. `tests/test_topics.py`

### Fixtures
- `temp_db` — in-memory SQLite with all 5 tables; 10 fake records (8 kept with embedding_key + timestamps spanning 2 weeks, 2 filtered); pre-populated `sentiment_predictions` for join tests
- `temp_cache_dir` — `tmpdir` with `embeddings_cache.npy` (shape `(8, 384)`, `np.ones`) + `embeddings_index.json` (mapping 8 kept IDs → rows 0–7)

### Unit Tests
- `test_embedding_cache_load` — shape and index contents correct
- `test_embedding_cache_get_subset` — returns correct shape and rows
- `test_embedding_cache_get_subset_missing_key` — skips missing key, no KeyError
- `test_compute_coherence_returns_float_in_range` — mock `_model.get_topic()`, assert result in [0.0, 1.0]
- `test_check_gate_passes` — 25 scores above threshold → passes
- `test_check_gate_fails_too_few_topics` — 15 scores → fails
- `test_check_gate_fails_low_coherence` — 25 scores but only 10 above threshold → fails

### DB Helper Tests
- `test_ensure_topics_tables_creates_tables` — all 3 tables in `sqlite_master`
- `test_ensure_topics_tables_idempotent` — called twice, no exception
- `test_iter_preprocessed_for_topics_excludes_filtered` — 8 of 10 records returned
- `test_iter_preprocessed_for_topics_respects_days_window` — old records excluded
- `test_upsert_topics` — 3 rows in, 3 rows back
- `test_upsert_topic_assignments` — 5 docs assigned correctly
- `test_upsert_topic_over_time` — composite PK, 4 rows across 2 topics × 2 weeks

### Integration Tests
Patch 4 things: `TopicModeler._build_model` (returns MagicMock), `TopicModeler.train` (returns fake assignments for 8 docs, 2 topics), `TopicModeler.get_topic_info` (2 fake topics), `TopicModeler.compute_coherence` (returns 0.65).

- `test_run_topic_modeling_integration` — asserts `total_docs==8`, `n_topics==2`, `gate_passed==True`, DB row counts correct for all 3 tables
- `test_run_topic_modeling_idempotent` — run twice; topics and assignments count same after second run (not doubled)
- `test_run_topic_modeling_excludes_filtered` — `total_docs==8` not 10

---

## 6. Housekeeping Steps (before coding)

1. **Update `docs/prd_v2.md`** — flip Week 1 and Week 2 checkboxes to `[x]` (those weeks are complete per current repo state)
2. **Copy this plan to `docs/week3_topic_modeling_plan.md`** — so it lives alongside other project docs

---

## Verification

```bash
# Install new deps
uv pip install -e ".[ml,production]"

# Run tests
pytest tests/test_topics.py -v

# Run full pipeline (requires real DB + embedding cache from Weeks 1-2)
python scripts/train_topic_model.py --db historical_reddit_data.db --cache-dir models/

# Check DB results
python -c "
import sqlite3
conn = sqlite3.connect('historical_reddit_data.db')
print('topics:', conn.execute('SELECT COUNT(*) FROM topics').fetchone()[0])
print('assignments:', conn.execute('SELECT COUNT(*) FROM topic_assignments').fetchone()[0])
print('over_time rows:', conn.execute('SELECT COUNT(*) FROM topic_over_time').fetchone()[0])
"
```

Gate check: script exits 0 only if ≥20 topics have coherence ≥0.50.
