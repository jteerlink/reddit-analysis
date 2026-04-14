# Week 5 Plan — Streamlit Dashboard

**Status:** Not started
**Goal:** An on-demand local dashboard (`streamlit run app.py`) with five tabs, all reading live from SQLite. Charts must render from real data; graceful degradation when ML pipeline hasn't been run yet.

---

## Scope

From the PRD:
- `app.py` — Streamlit entry point with all five tabs
- All tabs connected to live SQLite data
- Export functionality (CSV/JSON) on the Deep Dive tab

**Gate:** Dashboard launches cleanly (`streamlit run app.py` starts without errors), all charts render from real data, export downloads work.

---

## Architecture

### File layout

Keep `app.py` under 500 lines by delegating all data access to a `src/dashboard/` subpackage:

```
app.py                       ← Streamlit entry point; tab routing only
src/dashboard/
    __init__.py
    db.py                    ← Cached SQLite queries (one function per chart)
    charts.py                ← Reusable Plotly/Altair chart builders
```

No business logic in `app.py`. No raw SQL in `app.py`. Charts are pure functions that accept a DataFrame and return a figure — they can be tested independently.

### Sidebar (shared across all tabs)

- **Subreddit multi-select** (default: all)
- **Date range slider** (min/max derived from `posts.timestamp`)
- **Last refreshed** timestamp + manual refresh button that clears `st.cache_data`

### Database connection

`src/dashboard/db.py` opens a read-only SQLite connection per query call. All query functions are decorated with `@st.cache_data(ttl=300)` (5-minute TTL). Each function checks for table existence before querying and returns an empty DataFrame with the correct schema if a table is missing — this is the graceful degradation strategy.

---

## Tab Specifications

### Tab 1 — Overview

Metric cards row:
- Total posts + comments collected
- Current sentiment ratio (positive / neutral / negative %) — from `sentiment_predictions`
- Top 3 trending topics (highest doc_count in the most recent week) — from `topic_over_time`
- Last collection timestamp — from `MAX(posts.timestamp)`
- Last ML run timestamp — from `MAX(sentiment_predictions.predicted_at)`

Below the cards:
- Stacked bar chart: daily post volume per subreddit over the last 30 days (from `posts.timestamp`)
- Sentiment distribution donut chart

All metric cards show "—" with a muted info message if the source table is empty, so the tab is always usable even before the ML pipeline runs.

### Tab 2 — Sentiment Trends

Controls (above chart):
- Date range selector (Streamlit `date_input`, pre-filled from sidebar range)
- Subreddit checkboxes (inherited from sidebar)
- Moving average toggle: 7-day / 30-day / both / none

Charts:
- **Line chart:** daily mean sentiment per subreddit, with selected moving average overlaid — data from `sentiment_daily` JOIN `sentiment_moving_avg`
- **Change point annotations:** vertical dashed lines on the same chart — data from `change_points`; color-coded by magnitude (green = positive shift, red = negative shift)
- **Forecast panel:** separate chart below showing the Prophet forecast from `sentiment_forecast` with shaded 95% confidence band; historical actuals overlaid for context

If `sentiment_daily` is empty, show an info box: "Run `python scripts/run_timeseries.py` to populate sentiment trends."

### Tab 3 — Topic Explorer

Left column (30% width):
- Scrollable table of all topics: keyword preview (first 5 words), doc count, coherence score
- Clicking a row selects that topic and updates the right column

Right column (70% width):
- **Topic-over-time bar chart:** weekly doc count for the selected topic — from `topic_over_time`
- **Word cloud:** generated from the full keyword list of the selected topic (uses `wordcloud` library); cached per topic_id
- **Emerging topics panel:** topics that first appeared in the most recent 7 days, highlighted with a badge

Full-width below:
- **Heatmap:** topics (rows) × weeks (columns), cell = avg_sentiment — from `topic_over_time.avg_sentiment`; limited to top 30 topics by total doc_count for readability

### Tab 4 — Deep Dive

Filter controls:
- Keyword text input (searches `preprocessed.clean_text`)
- Subreddit multi-select (inherits sidebar)
- Date range (inherits sidebar)
- Sentiment label filter (positive / neutral / negative / all)
- Content type toggle (posts / comments / both)

Results table:
- Columns: date, subreddit, content_type, clean_text (truncated to 200 chars), label, confidence
- Sorted by date descending; paginated (50 rows per page via `st.dataframe` with `use_container_width=True`)
- Row click expands to full text in an expander below the table

Export:
- **Download CSV** button — exports current filtered result set (no row limit)
- **Download JSON** button — same data, JSON Lines format

### Tab 5 — Model Health

Metric row:
- Mean prediction confidence across all records
- % of predictions with confidence ≥ 0.75 (alert if below threshold)
- VADER / model agreement rate (% where VADER polarity direction matches model label)
- Last retrain date (from `mlruns/` metadata via MLflow client, or "never" if no runs)

Charts:
- **Confidence histogram:** distribution of `sentiment_predictions.confidence` — binned into 20 buckets; flag the 0.75 threshold with a vertical line
- **VADER agreement bar chart:** per-subreddit agreement rate between VADER compound sign and model label
- **Drift indicator:** placeholder card showing "No drift data yet — run `scripts/detect_drift.py`" (Week 6 concern)

---

## Data Access Functions (`src/dashboard/db.py`)

One function per data need. Each returns a DataFrame. All are `@st.cache_data` decorated.

| Function | Source tables | Returns |
|---|---|---|
| `get_collection_summary()` | `posts`, `comments` | total counts, last timestamp |
| `get_sentiment_summary()` | `sentiment_predictions` | label counts, mean confidence |
| `get_trending_topics()` | `topic_over_time`, `topics` | top N topics this week |
| `get_daily_volume(subreddits, days)` | `posts`, `comments` | date × subreddit counts |
| `get_sentiment_daily(subreddits, days)` | `sentiment_daily`, `sentiment_moving_avg` | date × subreddit sentiment |
| `get_change_points(subreddits)` | `change_points` | subreddit, date, magnitude |
| `get_forecast(subreddits)` | `sentiment_forecast` | subreddit, date, yhat, bounds |
| `get_topics()` | `topics` | all topics with keywords + stats |
| `get_topic_over_time(topic_id)` | `topic_over_time` | weekly time series for one topic |
| `get_topic_heatmap(n)` | `topic_over_time` | pivot: topic_id × week_start |
| `get_deep_dive(filters)` | `preprocessed`, `sentiment_predictions`, `posts`, `comments` | filtered result set |
| `get_vader_agreement()` | `preprocessed`, `sentiment_predictions`, `posts` | subreddit-level agreement rates |

---

## Chart Library Choice

Use **Plotly Express** for all interactive charts (line, bar, heatmap, histogram). Use `matplotlib`/`wordcloud` for word clouds (rendered as a static PNG via `st.image`). Avoids pulling in Altair as an additional dependency — Plotly is already in the `dev` extras.

---

## Graceful Degradation Rules

Every tab section that depends on an ML table must check whether the table is populated before rendering. Display pattern:

- If the source table exists and has rows → render the chart normally
- If the table is empty → show `st.info("Run [script] to populate this section.")` in place of the chart
- If the table doesn't exist at all → same `st.info` message (the `db.py` functions handle the missing-table case by returning an empty DataFrame)

This ensures `streamlit run app.py` always works, even on a fresh database with only `posts` and `comments`.

---

## Dependencies to Add

Add to `pyproject.toml` under the `dev` extras:
- `wordcloud>=1.9.0` — word cloud generation for Topic Explorer
- `plotly>=5.10.0` — already declared; verify it's present

`streamlit>=1.12.0` is already declared under `production` extras.

---

## Implementation Order

1. `src/dashboard/__init__.py` and `src/dashboard/db.py` — all data access functions with empty-table handling
2. `src/dashboard/charts.py` — reusable Plotly figure builders
3. `app.py` — sidebar + tab skeleton, wire up Tab 1 (Overview) first
4. Tab 2 (Sentiment Trends) — depends on timeseries tables
5. Tab 3 (Topic Explorer) — depends on topics tables
6. Tab 4 (Deep Dive) — depends on preprocessed + sentiment tables; export buttons last
7. Tab 5 (Model Health) — depends on sentiment_predictions + MLflow

---

## Verification

```
streamlit run app.py
```

Checklist:
- Dashboard starts in < 5 seconds (Streamlit startup, not data load)
- Tab 1 renders metric cards with real post/comment counts
- Tab 2 renders once timeseries tables are populated (run `scripts/run_timeseries.py` first)
- Tab 3 renders once topic tables are populated (run `scripts/train_topic_model.py` first)
- Tab 4 search returns results; CSV and JSON downloads work
- Tab 5 renders confidence histogram once `sentiment_predictions` is populated
- Switching tabs does not cause full page reloads (Streamlit tab behavior is client-side)
- Sidebar subreddit filter propagates correctly to all charts
