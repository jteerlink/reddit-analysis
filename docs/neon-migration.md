# Neon PostgreSQL Migration Plan

## Context

The project currently uses a local SQLite file (`historical_reddit_data.db`, 221 MB) as its only database. Migrating to Neon (serverless PostgreSQL) achieves two goals: the Next.js dashboard can eventually be hosted remotely with real-time data, and the database is no longer tied to a single machine.

The migration touches 15 files across the Python backend, ML pipeline scripts, and shell scripts. The Next.js frontend calls FastAPI and is unaffected. The Streamlit app (`app.py`) is retained during transition but will point to Neon once migration is complete.

---

## Phase 0 — Prerequisites

**You provide after running `npx neonctl@latest init`:**
- `DATABASE_URL` — primary connection string (write access, format: `postgresql://user:pass@host/dbname?sslmode=require`)
- `DATABASE_URL_POOLED` — connection pooler endpoint for high-concurrency FastAPI use
- Project name and branch ID (for branching strategy)

**Add to `.env`:**
- `DATABASE_URL` — primary write connection
- `DATABASE_URL_POOLED` — pooled connection for FastAPI API layer
- Remove `REDDIT_DB_PATH` once migration is complete (keep during transition)

**Add to `.env.example`:**
- Document both new variables, mark `REDDIT_DB_PATH` as deprecated

---

## Phase 1 — Python Dependencies

**Add to `pyproject.toml` under `production` optional dependencies:**
- `psycopg2-binary>=2.9.0` — sync PostgreSQL adapter (used by data collection, ML pipeline, dashboard read layer)
- `psycopg2-pool` is included in psycopg2; use `ThreadedConnectionPool` for the pipeline scripts
- Retain `pandas` — `pd.read_sql_query` works with psycopg2 connections after switching parameterization to `%s`

**No new dependencies needed for the Next.js dashboard** — it calls FastAPI, not the DB directly.

---

## Phase 2 — Schema Migration

Run against Neon before any code changes. All 13 tables must exist in Neon before data migration or code cutover.

### Type conversions applied universally

| SQLite type | PostgreSQL type | Notes |
|---|---|---|
| `TEXT PRIMARY KEY` | `TEXT PRIMARY KEY` | No change |
| `INTEGER PRIMARY KEY AUTOINCREMENT` | `BIGSERIAL PRIMARY KEY` | Auto-increment |
| `INTEGER` | `INTEGER` | No change |
| `REAL` | `DOUBLE PRECISION` | Floating point |
| `DATETIME` / `DATETIME DEFAULT CURRENT_TIMESTAMP` | `TIMESTAMPTZ DEFAULT NOW()` | Time-zone aware |
| `TEXT` (storing JSON, e.g. logits, keywords) | `JSONB` | Binary JSON; enables index queries |
| `INTEGER DEFAULT 0` (boolean flag) | `BOOLEAN DEFAULT FALSE` | Use native bool |
| Composite `PRIMARY KEY (a, b)` | Unchanged | Works in PostgreSQL |

### Table-by-table notes

**posts** — `content_type TEXT DEFAULT 'post'` becomes a `TEXT` column with a `CHECK (content_type IN ('post','comment'))` constraint added.

**comments** — `FOREIGN KEY (post_id) REFERENCES posts(id)` is kept; PostgreSQL enforces it by default (no PRAGMA needed).

**api_metrics** — `id INTEGER PRIMARY KEY AUTOINCREMENT` → `id BIGSERIAL PRIMARY KEY`.

**collection_metadata** and **batch_collections** — same autoincrement swap; `UNIQUE(subreddit, collection_timestamp)` is kept as-is.

**preprocessed** — `is_filtered INTEGER DEFAULT 0` becomes `is_filtered BOOLEAN DEFAULT FALSE`; all reads/writes updated accordingly.

**sentiment_predictions** — `logits TEXT` becomes `logits JSONB`. Stored value is a JSON array of 3 floats; switch serialization from `json.dumps(list)` to passing Python list directly (psycopg2 with `psycopg2.extras.Json` or `json.dumps`).

**topics** — `keywords TEXT` (currently stores a JSON array or comma-separated string) becomes `keywords TEXT` retained as-is initially; migrate to `keywords JSONB` in a follow-up once keyword parsing is standardized.

**topic_over_time**, **sentiment_daily**, **sentiment_moving_avg**, **change_points**, **sentiment_forecast**, **topic_sentiment_trends** — all composite primary keys retained; `REAL` columns become `DOUBLE PRECISION`; `TEXT` date columns (`date TEXT`, `week_start TEXT`) become `DATE` type for proper ordering.

### Indexes to recreate

All `CREATE INDEX` statements from `src/ml/db.py` are recreated in PostgreSQL with the same columns. Additionally add a GIN index on `sentiment_predictions.logits` if JSON querying is needed later.

### Removed SQLite-isms

- All `PRAGMA journal_mode=WAL` and `PRAGMA foreign_keys=ON` statements are removed; PostgreSQL handles these natively.
- `VACUUM` calls in `split_db.py` are kept — PostgreSQL supports `VACUUM` (and Neon runs autovacuum).

---

## Phase 3 — Data Migration

Run once, after schema is created in Neon, before code cutover. Order matters due to foreign keys.

### Migration order (respects FK dependencies)

1. `posts`
2. `comments` (FK → posts)
3. `preprocessed`
4. `sentiment_predictions`
5. `api_metrics`
6. `collection_metadata`
7. `batch_collections`
8. `topics`
9. `topic_assignments` (FK → preprocessed)
10. `topic_over_time`
11. `sentiment_daily`
12. `sentiment_moving_avg`
13. `change_points`
14. `sentiment_forecast`
15. `topic_sentiment_trends`

### Migration script location

Create `scripts/migrate_to_neon.py`. It reads each table from SQLite using `pd.read_sql_query` and writes to Neon using `psycopg2.extras.execute_values` in batches of 1,000 rows.

- Boolean conversion: `is_filtered INTEGER` (0/1) → Python `bool` before insert
- JSONB conversion: `logits TEXT` parsed with `json.loads` then passed as Python list
- Timestamp conversion: `datetime('now')` strings parsed with `dateutil.parser.parse` and made timezone-aware (UTC) before insert
- Date columns: `TEXT` date strings in `sentiment_daily` etc. parsed to `datetime.date` objects

The script prints progress per table and row count before/after. It is safe to re-run: uses `ON CONFLICT DO NOTHING` for all inserts.

---

## Phase 4 — Connection Layer Changes

### New shared connection module: `src/db/connection.py`

Replace all individual `sqlite3.connect()` calls with a single shared module that returns a psycopg2 connection (sync) or pool. All other modules import from here.

- Write connection: uses `DATABASE_URL` env var
- Read-only connection: uses `DATABASE_URL_POOLED` env var (or same URL with `application_name=readonly` for clarity)
- `ThreadedConnectionPool(minconn=1, maxconn=10)` for ML pipeline scripts (long-running processes)
- Single connection per-request pattern for FastAPI routes (FastAPI handles concurrency via async; wrap in `asyncio.get_event_loop().run_in_executor` if needed, or switch routes to `asyncpg` later)

### Parameterization: `?` → `%s`

Every SQL file that uses `?` placeholders must switch to `%s` (psycopg2 standard). This affects:
- `src/reddit_api/storage.py` — all INSERT and SELECT statements (approx 20 statements)
- `src/ml/db.py` — all `executemany` calls (approx 10 batch insert patterns)
- `src/dashboard/db.py` — all `pd.read_sql_query` params lists (approx 12 queries)
- `src/api/db.py` — same as dashboard/db.py (approx 12 queries)
- `scripts/generate_weak_labels.py` — 1 SELECT with LIMIT

### Date arithmetic: SQLite → PostgreSQL

Every occurrence of `datetime('now', ?)` or `DATE('now', ?)` with a string like `"-30 days"` must become `NOW() - INTERVAL '30 days'` or `CURRENT_DATE - INTERVAL '30 days'`. Because the interval is now part of the SQL rather than a parameter, these queries need to inline the day count:

- Pattern in dashboard/db.py and api/db.py: `days` parameter is Python int; embed it as `f"NOW() - INTERVAL '{days} days'"` (safe — it's an integer, not user string input)
- Pattern in ml/db.py: same approach for the `days` argument passed to pipeline functions

### `strftime` → `TO_CHAR`

In `scripts/monthly_counts.py`, `strftime('%Y-%m', timestamp)` becomes `TO_CHAR(timestamp, 'YYYY-MM')`.

### `INSERT OR REPLACE` → `INSERT ... ON CONFLICT`

Every `INSERT OR REPLACE` in `storage.py` and `ml/db.py` must become an explicit upsert. For tables with a single primary key column, use `ON CONFLICT (id) DO UPDATE SET col = EXCLUDED.col`. For composite primary key tables, list all PK columns in the conflict target.

- `posts` and `comments`: conflict on `id`, update all mutable columns
- `preprocessed`: conflict on `id`, update all columns
- `sentiment_predictions`: conflict on `id`, update all columns
- `topics`: conflict on `topic_id`, update keywords, doc_count, coherence_score
- `topic_assignments`, `topic_over_time`, `sentiment_daily`, etc.: conflict on composite PK, update all non-PK columns

### `sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)`

The read-only URI pattern has no direct PostgreSQL equivalent. Replace with a standard connection using `DATABASE_URL_POOLED`. Neon's pooler endpoint is connection-pooled and safe for concurrent reads. The `@st.cache_data(ttl=300)` decorators on `src/dashboard/db.py` functions remain unchanged.

### `sqlite_master` queries in `run_pipeline.sh`

The `table_exists()` shell function uses `SELECT name FROM sqlite_master WHERE type='table'`. Replace with `SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename='$1'`.

The `python_query()` shell function uses an inline Python heredoc that opens a sqlite3 connection. Replace with a psycopg2 equivalent heredoc using `DATABASE_URL`.

---

## Phase 5 — File-by-File Change Summary

| File | Change type | Key changes |
|---|---|---|
| `src/db/connection.py` | **New file** | Shared psycopg2 pool; `get_conn()` and `release_conn()` helpers |
| `src/reddit_api/storage.py` | Rewrite connection + queries | `?` → `%s`, `INSERT OR REPLACE` → upserts, PRAGMA removal, `AUTOINCREMENT` removed |
| `src/ml/db.py` | Rewrite connection + queries | Same as storage.py; date arithmetic; boolean flag for `is_filtered` |
| `src/dashboard/db.py` | Swap connection; update queries | `?` → `%s`, date arithmetic, keep `@st.cache_data` |
| `src/api/db.py` | Swap connection; update queries | Same as dashboard/db.py |
| `scripts/generate_weak_labels.py` | Swap connection; update queries | `?` → `%s`, `COALESCE` subquery unchanged |
| `scripts/monthly_counts.py` | Swap connection; update queries | `strftime` → `TO_CHAR` |
| `scripts/query_database_counts.py` | Swap connection | Queries unchanged |
| `scripts/query_database_detailed.py` | Swap connection; update queries | `datetime('now', '-7 days')` → `NOW() - INTERVAL '7 days'` |
| `split_db.py` | Swap connection; fix injection | Replace string interpolation with parameterized IN clause; `PRAGMA` removal; `VACUUM` kept |
| `scripts/run_pipeline.sh` | Update shell DB helpers | `sqlite_master` → `pg_tables`; `python_query()` heredoc uses psycopg2 |
| `scripts/migrate_to_neon.py` | **New file** | One-time data migration script |
| `src/api/routes/health.py` | **New file** | `/health` endpoint reporting backend and DB reachability |
| `tests/test_api_db.py` | **New file** | Unit tests for all `src/api/db.py` functions |
| `tests/test_api_routes.py` | **New file** | FastAPI route tests using TestClient with mocked db layer |
| `.env.example` | Add vars | `DATABASE_URL`, `DATABASE_URL_POOLED`; deprecate `REDDIT_DB_PATH` |
| `pyproject.toml` | Add dependency | `psycopg2-binary` under `production`; `httpx` under `dev` (TestClient dependency) |

---

## Phase 5b — Fallback & Resilience

### Dual-backend connection factory (`src/api/db.py`)

`_connect()` is extended to detect and use whichever backend is available:

1. If `DATABASE_URL` env var is set **and** `psycopg2` is importable → open a psycopg2 connection to Neon; log `backend=postgres`
2. Otherwise → fall back to SQLite read-only URI; log `backend=sqlite`

A module-level `ACTIVE_BACKEND` string (`"sqlite"` or `"postgres"`) is set once at import time so callers and the health endpoint can report it without re-detecting on every request.

All existing query functions are unchanged during the SQLite phase — they continue to use `pd.read_sql_query` and `?` params. Only `_connect()` changes.

### Health endpoint (`src/api/routes/health.py` + `src/api/app.py`)

`GET /health` returns a JSON object:

- `status` — `"ok"` or `"degraded"`
- `backend` — `"sqlite"` or `"postgres"`
- `db_reachable` — `true` if a test query (`SELECT 1`) succeeds; `false` otherwise
- `db_path_or_url` — redacted last 4 chars of the active connection target (for debugging without leaking credentials)

The endpoint never raises an exception; any DB failure sets `db_reachable: false` and `status: "degraded"` with HTTP 200 (the frontend polls this and shows a banner rather than crashing).

The router is registered in `src/api/app.py` at `/health` (no prefix).

### Error propagation from db functions

Every function in `src/api/db.py` already wraps its body in a bare `except Exception`. During the migration period, add `logging.exception(...)` inside each except block so errors appear in the uvicorn log rather than being silently swallowed.

---

## Phase 5c — Test Strategy

### `tests/test_api_db.py` — DB function unit tests

Uses a temporary in-memory SQLite DB created in a `pytest` fixture. The fixture creates the minimal schema (just enough tables to satisfy each function) and optionally seeds one or two rows.

**What is tested per function:**

- Return type is always `list` or `dict` (never raises)
- Returns empty list/dict when tables are empty
- Returns correctly shaped dict/list keys when rows exist
- `get_date_range()` falls back to today ± 30 days when table is empty
- `get_collection_summary()` returns all four expected keys
- `get_deep_dive()` respects `label_filter`, `content_type_filter`, `limit`, `offset` params
- `get_vader_agreement()` returns empty list gracefully when VADER is unavailable (mocked)

The fixture patches `src.api.db.DB_PATH` to point at a temp file so no production data is touched.

### `tests/test_api_routes.py` — FastAPI route integration tests

Uses `fastapi.testclient.TestClient` (sync). The `src.api.db` module is patched at the module level so routes return mock data without hitting any real database.

**What is tested per route:**

| Route | Assertions |
|---|---|
| `GET /summary` | 200, has `total_posts`, `trending_topics` keys |
| `GET /sentiment/summary` | 200, list of dicts with `label`, `count` keys |
| `GET /sentiment/daily?subreddits=ChatGPT` | 200, list; subreddit filter forwarded |
| `GET /sentiment/change-points` | 200, list |
| `GET /sentiment/forecast` | 200, list |
| `GET /volume/daily` | 200, list |
| `GET /topics` | 200, list with `topic_id` key |
| `GET /topics/emerging` | 200, list |
| `GET /topics/heatmap` | 200, list |
| `GET /topics/42/over-time` | 200, list; path param forwarded |
| `GET /posts/search?keyword=inflation` | 200, list; keyword forwarded |
| `GET /model/vader-agreement` | 200, list with `subreddit`, `agreement_rate` keys |
| `GET /subreddits` | 200, list of strings |
| `GET /date-range` | 200, dict with `start`, `end` keys |
| `GET /pipeline/status` | 200, list of 7 step dicts each with `num`, `done`, `state` |
| `GET /health` | 200, has `status`, `backend`, `db_reachable` keys |

**Error path tests:**
- When db function raises, route still returns 200 with empty list (not 500)
- `GET /pipeline/run/99` returns 400 (invalid step)

### Running tests

```
pytest tests/test_api_db.py tests/test_api_routes.py -v
```

Both test files use only stdlib + existing dev dependencies (`pytest`, `httpx`). No additional test infrastructure is needed.

---

## Phase 6 — Cutover Sequence

1. Run `scripts/migrate_to_neon.py` — verify row counts match SQLite
2. Set `DATABASE_URL` and `DATABASE_URL_POOLED` in `.env`
3. Restart FastAPI — verify all API endpoints return data from Neon
4. Restart Streamlit — verify dashboard loads
5. Run `scripts/query_database_counts.py` against Neon — compare to SQLite counts
6. Run one full pipeline step (Step 5 Batch Inference, small batch) end-to-end against Neon to confirm writes work
7. Update `run_pipeline.sh` DB helper functions — run Step 1 Prerequisites check
8. Remove `REDDIT_DB_PATH` from `.env` after 1 week of clean operation

---

## Verification Checklist

**Tests (run before and after cutover):**
- `pytest tests/test_api_db.py tests/test_api_routes.py -v` passes with zero failures in both SQLite and Neon modes
- `GET /health` returns `db_reachable: true` with the correct `backend` value

**Data integrity:**
- `curl http://localhost:8000/subreddits` returns the same 20 subreddits from Neon
- `curl http://localhost:8000/summary` shows matching post/comment counts to SQLite
- Pipeline Step 5 (Batch Inference) writes predictions to Neon; `GET /sentiment/summary` reflects new data
- `scripts/monthly_counts.py` produces same monthly totals as before migration

**Code hygiene:**
- No `sqlite3` imports remain outside of `scripts/migrate_to_neon.py` and `tests/` (verify with `grep -r "import sqlite3" src/`)
- Uvicorn log shows `backend=postgres` on startup after cutover

---

## Open Questions (answer when you provide Neon creds)

- **Branch strategy**: Use Neon's branching for staging (a `dev` branch for pipeline runs, `main` for production reads)?
- **Read replicas**: Route FastAPI dashboard reads to Neon's read replica endpoint to reduce load on write path?
- **Compute size**: Neon auto-scales; no action needed, but note that VADER agreement query scans 10k rows — add index on `preprocessed.is_filtered` if slow.
- **Connection limit**: Neon free tier allows 100 connections; the pooled endpoint handles this. Confirm `ThreadedConnectionPool(maxconn=10)` is within budget.
