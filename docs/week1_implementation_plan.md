# Week 1 Implementation Plan — Preprocessing & Weak Labels

## Context

The PRD defines Phase 2 as the ML/visualization layer. Week 1 is the foundation: get raw Reddit text cleaned, embedded, and weakly labeled so Week 2 (DistilBERT fine-tuning) has a training set ready. The gate is ≥30k high-confidence VADER labels and a working embedding cache.

The existing codebase has Phase 1 complete: SQLite with `posts` and `comments` tables, circuit-breaker collection, and declared (but not installed) ML deps. VADER (`vaderSentiment`) is already a core dep. `sentence-transformers` and `spacy` are not yet declared.

The machine is Apple Silicon — all model inference and embedding generation will use the **MPS (Metal Performance Shaders)** backend via PyTorch for hardware acceleration.

---

## Deliverables

- [x] `pyproject.toml` — Add `sentence-transformers>=2.2.0`, `spacy>=3.5.0`, `umap-learn>=0.5.0`, `numpy>=1.23.0` to `[ml]` optional group
- [x] `src/ml/__init__.py` — Package init, exposes public API
- [x] `src/ml/db.py` — Thin DB utility for ML layer (reuses connection pattern from `src/reddit_api/storage.py`)
- [x] `src/ml/preprocessing.py` — Text cleaning + MPS-accelerated embedding generation + writes `preprocessed` table
- [x] `scripts/generate_weak_labels.py` — VADER scoring → filtered CSV of high-confidence labels
- [x] `notebooks/eda_database.ipynb` — EDA notebook (data distributions, quality checks, vocabulary)
- [x] `tests/test_preprocessing.py` — 20 unit + integration tests (all passing)

> Note: Add `PYTORCH_ENABLE_MPS_FALLBACK=1` to `.env` manually before running.

---

## Apple Silicon / MPS Acceleration

PyTorch supports the Metal Performance Shaders backend on M-series chips. Key rules for this project:

**Device selection (use this pattern everywhere):**
```
mps → cuda → cpu   (priority order)
```

Concretely:
```
if torch.backends.mps.is_available():
    device = "mps"
elif torch.cuda.is_available():
    device = "cuda"
else:
    device = "cpu"
```

**sentence-transformers**: Pass `device=device` to `SentenceTransformer(model_name, device=device)`. MPS gives ~3–5× speedup over CPU for `all-MiniLM-L6-v2` on M-series.

**Batch size on MPS**: MPS can handle larger batches than CPU. Use `batch_size=256` for embedding (vs 32 on CPU). sentence-transformers `encode()` accepts `batch_size` directly.

**Float precision**: MPS requires float32. Do not use `.half()` / `fp16` for MPS inference — it silently falls back to CPU or errors. Embeddings stored to disk as `float32`.

**spaCy + MPS**: spaCy uses its own runtime (not PyTorch MPS directly). For `en_core_web_sm`, CPU is used; this is fine since tokenization/lemmatization is not the bottleneck.

**MLflow**: Log `device` as a param in every run so experiments are reproducible.

**Week 2 prep note**: When fine-tuning DistilBERT, use `training_args = TrainingArguments(use_mps_device=True)` or set `PYTORCH_ENABLE_MPS_FALLBACK=1` env var to handle any ops not yet MPS-native.

---

## Database Change

Add one table to `reddit_data.db` (migration handled in `preprocessing.py` on first run, using `CREATE TABLE IF NOT EXISTS`):

```
preprocessed
  id           TEXT PRIMARY KEY   -- same ID as posts.id or comments.id
  content_type TEXT               -- 'post' or 'comment'
  raw_text     TEXT               -- concatenated title + content (posts) or content (comments)
  clean_text   TEXT               -- cleaned/normalized text
  token_count  INTEGER            -- token count post-cleaning
  is_filtered  INTEGER            -- 0=kept, 1=filtered (bot/short)
  filter_reason TEXT              -- null, 'bot', 'too_short', 'empty'
  embedding_key TEXT              -- key into embedding cache file (row index as string)
  processed_at DATETIME
```

Embedding cache: `models/embeddings_cache.npy` (numpy float32 array, row-indexed by `embedding_key`). A companion `models/embeddings_index.json` maps `id → row_index`.

---

## Implementation Detail

### `src/ml/db.py`
- `get_connection(db_path)` — returns sqlite3 connection with `row_factory = sqlite3.Row`
- `ensure_preprocessed_table(conn)` — `CREATE TABLE IF NOT EXISTS preprocessed ...`
- `iter_raw_records(conn, batch_size=1000)` — yields batches of `(id, title, content, content_type, author)` from posts + comments union, left-joining to exclude already-preprocessed IDs
- `upsert_preprocessed(conn, rows)` — batch insert/replace into `preprocessed`

### `src/ml/preprocessing.py`
Two classes:

**`TextCleaner`**
- `clean(text: str) -> str` — pipeline:
  1. Collapse `>` Reddit block quotes
  2. Strip URLs (`https?://\S+`)
  3. Strip markdown: `**bold**`, `*italic*`, `~~strike~~`, `[text](url)`, `` `code` ``
  4. Collapse whitespace/newlines
  5. Lowercase
  6. (Optional, gated by `lemmatize=True` flag) spaCy lemmatization via `en_core_web_sm`
- `is_bot(author: str) -> bool` — checks common bot suffixes: `bot`, `automoderator`, `[deleted]`
- `token_count(text: str) -> int` — whitespace split

**`EmbeddingGenerator`**
- `__init__(model_name="all-MiniLM-L6-v2", cache_dir="models/", device=None)` — auto-detects MPS/cuda/cpu if `device=None`; loads model lazily on first call
- `embed_batch(texts: list[str], batch_size=256) -> np.ndarray` — calls `model.encode(texts, batch_size=batch_size, show_progress_bar=False, convert_to_numpy=True)`, returns float32
- `load_cache() -> tuple[np.ndarray, dict]` — loads `.npy` + index JSON if exists
- `save_cache(embeddings, index)` — writes `.npy` + index JSON atomically (write temp → rename)

**`run_preprocessing(db_path, cache_dir, batch_size=1000, embed_batch_size=256, lemmatize=False)`**
Top-level orchestrator (wrapped in `mlflow.start_run`):
1. Detect device (mps/cuda/cpu), log as MLflow param
2. Open DB, `ensure_preprocessed_table`
3. For each batch from `iter_raw_records`:
   - Clean text, check bot/short (< 10 tokens) → set `is_filtered`
   - Collect non-filtered texts → call `embed_batch(texts, batch_size=embed_batch_size)`
   - Append to in-memory embedding array + update index
4. `upsert_preprocessed` for all rows in batch
5. Save cache after each batch (append-safe via index offsets)
6. Log final counts (`record_count`, `filtered_count`, `kept_count`, `embedding_dim`, `device`) to MLflow

### `scripts/generate_weak_labels.py`
CLI: `python scripts/generate_weak_labels.py --db reddit_data.db --output data/weak_labels.csv --threshold 0.5`

Steps (wrapped in `mlflow.start_run`):
1. Query `preprocessed` where `is_filtered = 0`
2. Apply `SentimentIntensityAnalyzer` (VADER) on `clean_text` → get `compound` score
3. Filter: keep rows where `abs(compound) > threshold`
4. Map: compound > threshold → `positive`, compound < -threshold → `negative`
5. Write CSV: `id, content_type, subreddit, clean_text, vader_compound, label`
6. Log to MLflow: `total_scored`, `kept_count`, `positive_count`, `negative_count`, `threshold`
7. Print summary with label distribution and gate status (≥30k check)

### `notebooks/eda_database.ipynb`
Sections:
1. **Data Volume** — total posts/comments, by subreddit, by month
2. **Text Quality** — raw text length distribution, null/empty rates, top authors by volume
3. **Filtering Preview** — estimated bot rate, short-post rate, expected clean corpus size
4. **Vocabulary** — top 50 unigrams/bigrams after cleaning (excluding stopwords)
5. **VADER Distribution** — run VADER on a 10k sample, show compound score histogram, estimate label yield at various thresholds
6. **Subreddit Sentiment Preview** — box plots of VADER scores per subreddit
7. **Embedding Sanity Check** — embed 100 samples on MPS, visualize with UMAP 2D scatter colored by subreddit

### MLflow Configuration
- No new files. MLflow is already declared in `pyproject.toml [production]`.
- Tracking URI: `mlruns/` (local, no server). Set via `mlflow.set_tracking_uri("mlruns")`.
- Experiment name: `reddit-analyzer-phase2`.
- Both `run_preprocessing()` and `generate_weak_labels.py` log to this experiment as separate named runs.

---

## Dependency Changes (`pyproject.toml`)

Edit `[project.optional-dependencies]` `ml` group — add:
- `sentence-transformers>=2.2.0`
- `spacy>=3.5.0`

`torch>=1.12.0` is already declared in `[ml]`; MPS is available from 1.12+ on Apple Silicon.

After editing:
```bash
uv pip install -e ".[ml,production]"
python -m spacy download en_core_web_sm
```

Set env var for MPS op fallback (add to `.env`):
```
PYTORCH_ENABLE_MPS_FALLBACK=1
```

---

## File Map (Critical Paths)

| Path | Action | Notes |
|------|--------|-------|
| `pyproject.toml` | Edit | Add sentence-transformers, spacy to [ml] |
| `.env` | Edit | Add PYTORCH_ENABLE_MPS_FALLBACK=1 |
| `src/ml/__init__.py` | Create | Package init |
| `src/ml/db.py` | Create | DB utilities for ML layer |
| `src/ml/preprocessing.py` | Create | TextCleaner + EmbeddingGenerator (MPS) + run_preprocessing |
| `scripts/generate_weak_labels.py` | Create | VADER weak labeling CLI |
| `notebooks/eda_database.ipynb` | Create | EDA notebook |
| `tests/test_preprocessing.py` | Create | Unit + integration tests |
| `src/reddit_api/storage.py` | Read only | Reference connection patterns only |

---

## Tests

`tests/test_preprocessing.py`:
- `test_text_cleaner_strips_urls`
- `test_text_cleaner_strips_markdown`
- `test_is_bot` — `AutoModerator`, `reddit_bot`, `[deleted]` → True; real username → False
- `test_token_count_threshold` — 9-token string → `is_filtered=True`
- `test_embedding_generator_device_detection` — asserts `device` is one of `mps/cuda/cpu`
- `test_run_preprocessing_integration` — uses `temp_db` fixture, 5 fake posts, asserts `preprocessed` table populated with correct `is_filtered` flags and non-null `embedding_key` for kept rows

---

## Verification (Gate Checks)

```bash
# 1. Install deps
uv pip install -e ".[ml,production]"
python -m spacy download en_core_web_sm

# 2. Confirm MPS is available
python -c "import torch; print('MPS:', torch.backends.mps.is_available())"

# 3. Run preprocessing (will use MPS automatically)
python -c "from src.ml.preprocessing import run_preprocessing; run_preprocessing('reddit_data.db', 'models/')"

# 4. Generate weak labels
python scripts/generate_weak_labels.py --db reddit_data.db --output data/weak_labels.csv

# 5. Verify gate: ≥30k labeled examples
python -c "import pandas as pd; df = pd.read_csv('data/weak_labels.csv'); print(len(df), df.label.value_counts())"

# 6. Confirm embedding cache
ls -lh models/embeddings_cache.npy models/embeddings_index.json

# 7. Run tests
pytest tests/test_preprocessing.py -v

# 8. Check MLflow
mlflow ui --backend-store-uri mlruns/
```

Gate passes when: CSV row count ≥ 30,000 AND `models/embeddings_cache.npy` exists AND `pytest` passes.
