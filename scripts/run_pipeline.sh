#!/usr/bin/env bash
# run_pipeline.sh — Interactive guide for the Reddit Analyzer ML pipeline
#
# Usage:
#   ./scripts/run_pipeline.sh              # interactive menu
#   ./scripts/run_pipeline.sh --check      # show status table only
#   ./scripts/run_pipeline.sh --step N     # run a specific step (1-7)
#   ./scripts/run_pipeline.sh --all        # run all steps in sequence
#   ./scripts/run_pipeline.sh --verbose    # show full command output

set -euo pipefail

# ── Paths ──────────────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DB="${DB_PATH:-$PROJECT_ROOT/historical_reddit_data.db}"
STATUS_DIR="$PROJECT_ROOT/.pipeline_status"
LOG_DIR="$PROJECT_ROOT/.pipeline_logs"

# ── Flags ──────────────────────────────────────────────────────────────────────
MODE="interactive"   # interactive | check | step | all
TARGET_STEP=""
VERBOSE=false
DB_PATH_OVERRIDE=false

# ── Colors ─────────────────────────────────────────────────────────────────────
if [[ -t 1 && -z "${NO_COLOR:-}" ]]; then
  RED=$(tput setaf 1); GREEN=$(tput setaf 2); YELLOW=$(tput setaf 3)
  BLUE=$(tput setaf 4); BOLD=$(tput bold); DIM=$(tput dim); RESET=$(tput sgr0)
else
  RED="" GREEN="" YELLOW="" BLUE="" BOLD="" DIM="" RESET=""
fi

# ── Helpers ────────────────────────────────────────────────────────────────────
info()    { printf "  %s\n" "$*"; }
success() { printf "  ${GREEN}✓${RESET}  %s\n" "$*"; }
warn()    { printf "  ${YELLOW}⚠${RESET}  %s\n" "$*"; }
error()   { printf "  ${RED}✗${RESET}  %s\n" "$*" >&2; }
header()  { printf "\n${BOLD}%s${RESET}\n" "$*"; }
dim()     { printf "  ${DIM}%s${RESET}\n" "$*"; }

die() { error "$*"; exit 1; }

require_db() {
  [[ -f "$DB" ]] || die "Database not found: $DB\n  Set DB_PATH or run from project root."
}

python_query() {
  # Run a SQLite query via Python; returns stdout trimmed
  python3 - <<EOF
import sqlite3, sys
try:
    conn = sqlite3.connect('$DB')
    result = conn.execute("""$1""").fetchone()
    print(result[0] if result and result[0] is not None else 0)
except Exception as e:
    print(0)
EOF
}

table_exists() {
  python3 - <<EOF
import sqlite3
try:
    conn = sqlite3.connect('$DB')
    r = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='$1'").fetchone()
    print("yes" if r else "no")
except:
    print("no")
EOF
}

mark_done()  { mkdir -p "$STATUS_DIR"; touch "$STATUS_DIR/step_${1}.done"; }
is_done()    { [[ -f "$STATUS_DIR/step_${1}.done" ]]; }
done_time()  { is_done "$1" && date -r "$STATUS_DIR/step_${1}.done" "+%Y-%m-%d %H:%M" 2>/dev/null || echo "—"; }

trap_cleanup() { printf "\n\n  Pipeline interrupted. Status files preserved.\n\n"; exit 130; }
trap trap_cleanup INT TERM

# ── Gate checks ────────────────────────────────────────────────────────────────

gate_1_prerequisites() {
  # Gate: python reachable, uv/pip reachable, DB exists, dirs exist
  python3 -c "import sqlite3" 2>/dev/null || return 1
  [[ -f "$DB" ]] || return 1
  return 0
}

gate_2_preprocessing() {
  # Gate: embeddings cache exists
  [[ -f "$PROJECT_ROOT/models/embeddings.npy" ]] || return 1
  return 0
}

gate_3_weak_labels() {
  # Gate: weak_labels.csv exists with >=30k rows
  local csv="$PROJECT_ROOT/data/weak_labels.csv"
  [[ -f "$csv" ]] || return 1
  local count
  count=$(python3 -c "
import csv
try:
    with open('$csv') as f:
        print(sum(1 for _ in csv.reader(f)) - 1)
except:
    print(0)
")
  [[ "$count" -ge 30000 ]] || return 1
  return 0
}

gate_4_sentiment_model() {
  # Gate: model directory and config file exist
  [[ -d "$PROJECT_ROOT/models/sentiment_v1" ]] || return 1
  [[ -f "$PROJECT_ROOT/models/sentiment_v1/config.json" ]] || return 1
  return 0
}

gate_5_batch_inference() {
  # Gate: sentiment_predictions table has rows
  [[ "$(table_exists sentiment_predictions)" == "yes" ]] || return 1
  local n
  n=$(python_query "SELECT COUNT(*) FROM sentiment_predictions")
  [[ "$n" -gt 0 ]] || return 1
  return 0
}

gate_6_topic_modeling() {
  # Gate: >=20 coherent topics in topics table
  [[ "$(table_exists topics)" == "yes" ]] || return 1
  local n
  n=$(python_query "SELECT COUNT(*) FROM topics WHERE coherence_score >= 0.50")
  [[ "$n" -ge 20 ]] || return 1
  return 0
}

gate_7_timeseries() {
  # Gate: sentiment_forecast table has rows
  [[ "$(table_exists sentiment_forecast)" == "yes" ]] || return 1
  local n
  n=$(python_query "SELECT COUNT(*) FROM sentiment_forecast")
  [[ "$n" -gt 0 ]] || return 1
  return 0
}

check_gate() {
  local step="$1"
  case "$step" in
    1) gate_1_prerequisites ;;
    2) gate_2_preprocessing ;;
    3) gate_3_weak_labels ;;
    4) gate_4_sentiment_model ;;
    5) gate_5_batch_inference ;;
    6) gate_6_topic_modeling ;;
    7) gate_7_timeseries ;;
    *) return 1 ;;
  esac
}

# ── Freshness checks ───────────────────────────────────────────────────────────

freshness_2_preprocessing() {
  # New rows in raw_posts/raw_comments not yet preprocessed
  [[ "$(table_exists raw_posts)" == "yes" ]] || { echo "—"; return; }
  local n
  n=$(python_query "
    SELECT COUNT(*) FROM raw_posts
    WHERE id NOT IN (SELECT id FROM preprocessed)
  " 2>/dev/null || echo 0)
  if [[ "$n" -gt 0 ]]; then
    printf "${YELLOW}STALE${RESET}  (+%s unprocessed rows)" "$n"
  else
    printf "${GREEN}Fresh${RESET}"
  fi
}

freshness_3_weak_labels() {
  local csv="$PROJECT_ROOT/data/weak_labels.csv"
  [[ -f "$csv" ]] || { echo "—"; return; }
  # Compare csv mtime to newest preprocessed row
  [[ "$(table_exists preprocessed)" == "yes" ]] || { printf "${GREEN}Fresh${RESET}"; return; }
  local newest_db csv_mtime
  newest_db=$(python_query "SELECT MAX(created_utc) FROM preprocessed WHERE is_filtered=0" 2>/dev/null || echo 0)
  csv_mtime=$(python3 -c "import os; print(int(os.path.getmtime('$csv')))" 2>/dev/null || echo 0)
  if [[ "$newest_db" -gt "$csv_mtime" ]]; then
    printf "${YELLOW}STALE${RESET}  (new preprocessed rows since last label run)"
  else
    printf "${GREEN}Fresh${RESET}"
  fi
}

freshness_4_sentiment_model() {
  local model_dir="$PROJECT_ROOT/models/sentiment_v1"
  [[ -d "$model_dir" ]] || { echo "—"; return; }
  local csv="$PROJECT_ROOT/data/weak_labels.csv"
  [[ -f "$csv" ]] || { printf "${GREEN}Fresh${RESET}"; return; }
  local model_mtime csv_mtime
  model_mtime=$(python3 -c "import os; print(int(os.path.getmtime('$model_dir')))" 2>/dev/null || echo 0)
  csv_mtime=$(python3 -c "import os; print(int(os.path.getmtime('$csv')))" 2>/dev/null || echo 0)
  if [[ "$csv_mtime" -gt "$model_mtime" ]]; then
    printf "${YELLOW}STALE${RESET}  (weak labels updated since last training)"
  else
    printf "${GREEN}Fresh${RESET}"
  fi
}

freshness_5_batch_inference() {
  [[ "$(table_exists preprocessed)" == "yes" ]] || { echo "—"; return; }
  [[ "$(table_exists sentiment_predictions)" == "yes" ]] || { echo "—"; return; }
  local n
  n=$(python_query "
    SELECT COUNT(*) FROM preprocessed p
    WHERE is_filtered=0
      AND NOT EXISTS (
        SELECT 1 FROM sentiment_predictions sp WHERE sp.id = p.id
      )
  " 2>/dev/null || echo 0)
  if [[ "$n" -gt 0 ]]; then
    printf "${YELLOW}STALE${RESET}  (%s unscored rows)" "$n"
  else
    printf "${GREEN}Fresh${RESET}"
  fi
}

freshness_6_topic_modeling() {
  [[ "$(table_exists sentiment_predictions)" == "yes" ]] || { echo "—"; return; }
  [[ "$(table_exists topics)" == "yes" ]] || { echo "—"; return; }
  # Compare newest prediction timestamp to topic model file mtime
  local newest_pred model_mtime
  newest_pred=$(python_query "
    SELECT MAX(created_at) FROM sentiment_predictions
  " 2>/dev/null || echo 0)
  local model_file="$PROJECT_ROOT/models/topic_model"
  if [[ -d "$model_file" || -f "$model_file" ]]; then
    model_mtime=$(python3 -c "import os; print(int(os.path.getmtime('$model_file')))" 2>/dev/null || echo 0)
    if [[ "$newest_pred" -gt "$model_mtime" ]]; then
      printf "${YELLOW}STALE${RESET}  (new predictions since last topic run)"
    else
      printf "${GREEN}Fresh${RESET}"
    fi
  else
    printf "${GREEN}Fresh${RESET}"
  fi
}

freshness_7_timeseries() {
  [[ "$(table_exists sentiment_forecast)" == "yes" ]] || { echo "—"; return; }
  local max_date today
  max_date=$(python_query "SELECT MAX(date) FROM sentiment_forecast" 2>/dev/null || echo "")
  today=$(python3 -c "from datetime import date; print(date.today())")
  if [[ -z "$max_date" || "$max_date" == "0" ]]; then
    echo "—"
  elif [[ "$max_date" < "$today" ]]; then
    printf "${YELLOW}STALE${RESET}  (forecast ends %s, today is %s)" "$max_date" "$today"
  else
    printf "${GREEN}Fresh${RESET}"
  fi
}

get_freshness() {
  case "$1" in
    1) echo "—" ;;
    2) freshness_2_preprocessing ;;
    3) freshness_3_weak_labels ;;
    4) freshness_4_sentiment_model ;;
    5) freshness_5_batch_inference ;;
    6) freshness_6_topic_modeling ;;
    7) freshness_7_timeseries ;;
  esac
}

# ── Step metadata ──────────────────────────────────────────────────────────────

step_name() {
  case "$1" in
    1) echo "Prerequisites" ;;
    2) echo "Preprocessing" ;;
    3) echo "Weak Labels" ;;
    4) echo "Train Sentiment Model" ;;
    5) echo "Batch Inference" ;;
    6) echo "Topic Modeling" ;;
    7) echo "Time Series & Forecasting" ;;
  esac
}

step_desc() {
  case "$1" in
    1) echo "Install ml+production deps, verify database, create models/ and data/ dirs" ;;
    2) echo "Clean raw posts/comments, generate sentence embeddings, write preprocessed table" ;;
    3) echo "Score preprocessed text with keyword rules and produce a labeled training CSV" ;;
    4) echo "Fine-tune DistilBERT on weak labels (~20-40 min on MPS/GPU)" ;;
    5) echo "Run the trained sentiment model across all preprocessed records" ;;
    6) echo "Discover dominant themes with BERTopic and track them week over week" ;;
    7) echo "Aggregate daily sentiment, detect trend shifts, generate 14-day Prophet forecasts" ;;
  esac
}

step_gate_desc() {
  case "$1" in
    1) echo "python3 reachable, database exists, models/ and data/ present" ;;
    2) echo "models/embeddings.npy exists" ;;
    3) echo "data/weak_labels.csv exists with ≥ 30,000 rows" ;;
    4) echo "models/sentiment_v1/config.json exists" ;;
    5) echo "sentiment_predictions table has rows" ;;
    6) echo "≥ 20 topics with coherence ≥ 0.50 in topics table" ;;
    7) echo "sentiment_forecast table has rows" ;;
  esac
}

step_hint() {
  case "$1" in
    2) echo "Run: uv pip install -e \".[ml,production]\"  |  Check DB path with: ls -lh $DB" ;;
    3) echo "Lower --threshold to 0.4 in the weak labels step to get more labeled rows" ;;
    4) echo "Lower --threshold 0.4 in weak labels step or check models/sentiment_v1/ for partial output" ;;
    5) echo "Reduce --batch-size to 8 if OOM on training; use --batch-size 512 for inference" ;;
    6) echo "Lower --min-cluster-size to 15, or add --skip-gate to inspect topics manually" ;;
    7) echo "Ensure batch inference ran first to populate sentiment_predictions" ;;
    *) echo "" ;;
  esac
}

# ── Status table ───────────────────────────────────────────────────────────────

print_status_table() {
  local check_db="${1:-true}"
  printf "\n"
  printf "  ${BOLD}%-3s  %-28s  %-6s  %-10s  %s${RESET}\n" "#" "Step" "Gate" "Last Run" "Freshness"
  printf "  %s\n" "──────────────────────────────────────────────────────────────────────────────"

  for i in 1 2 3 4 5 6 7; do
    local gate_str fresh_str last_run
    if [[ "$check_db" == "true" ]]; then
      if check_gate "$i" 2>/dev/null; then
        gate_str="${GREEN}PASS${RESET}"
      else
        gate_str="${RED}FAIL${RESET}"
      fi
      fresh_str=$(get_freshness "$i" 2>/dev/null || echo "—")
    else
      gate_str="${DIM}—${RESET}"
      fresh_str="${DIM}—${RESET}"
    fi
    last_run=$(done_time "$i")
    printf "  %-3s  %-28s  %b  %-10s  %b\n" \
      "$i" "$(step_name $i)" "$gate_str" "$last_run" "$fresh_str"
  done
  printf "\n"
}

# ── Step runners ───────────────────────────────────────────────────────────────

run_step() {
  local step="$1"
  local name
  name=$(step_name "$step")

  header "Step $step — $name"
  dim "$(step_desc $step)"
  printf "\n"

  mkdir -p "$LOG_DIR"
  local logfile="$LOG_DIR/step_${step}_$(date +%Y%m%d_%H%M%S).log"

  case "$step" in
    1) run_step_1 "$logfile" ;;
    2) run_step_2 "$logfile" ;;
    3) run_step_3 "$logfile" ;;
    4) run_step_4 "$logfile" ;;
    5) run_step_5 "$logfile" ;;
    6) run_step_6 "$logfile" ;;
    7) run_step_7 "$logfile" ;;
  esac
}

run_step_1() {
  local logfile="$1"
  info "Installing ml + production dependencies..."
  if $VERBOSE; then
    (cd "$PROJECT_ROOT" && uv pip install -e ".[ml,production]") | tee "$logfile"
  else
    (cd "$PROJECT_ROOT" && uv pip install -e ".[ml,production]") > "$logfile" 2>&1 \
      && success "Dependencies installed" \
      || { error "Install failed. Log: $logfile"; tail -20 "$logfile"; return 1; }
  fi

  info "Verifying database..."
  [[ -f "$DB" ]] && success "Database found: $(du -sh "$DB" | cut -f1) — $DB" \
    || { error "Database not found at $DB"; return 1; }

  info "Creating models/ and data/ directories..."
  mkdir -p "$PROJECT_ROOT/models" "$PROJECT_ROOT/data"
  success "Directories ready"

  mark_done 1
}

run_step_2() {
  local logfile="$1"
  info "Running preprocessing (this may take several minutes)..."
  if $VERBOSE; then
    (cd "$PROJECT_ROOT" && python3 - <<'PYEOF'
from src.ml.preprocessing import run_preprocessing
result = run_preprocessing(
    db_path="historical_reddit_data.db",
    cache_dir="models/",
    batch_size=1000,
    embed_batch_size=256,
    mlflow_tracking=True,
)
print(f"Total records:   {result['total']:,}")
print(f"Filtered:        {result['filtered']:,}")
print(f"Kept:            {result['kept']:,}")
print(f"Device:          {result['device']}")
PYEOF
) | tee "$logfile"
  else
    (cd "$PROJECT_ROOT" && python3 - <<'PYEOF'
from src.ml.preprocessing import run_preprocessing
result = run_preprocessing(
    db_path="historical_reddit_data.db",
    cache_dir="models/",
    batch_size=1000,
    embed_batch_size=256,
    mlflow_tracking=True,
)
print(f"Total records:   {result['total']:,}")
print(f"Filtered:        {result['filtered']:,}")
print(f"Kept:            {result['kept']:,}")
print(f"Device:          {result['device']}")
PYEOF
) > "$logfile" 2>&1 \
      && { grep -E "Total|Kept|Device" "$logfile" | while read -r line; do success "$line"; done; } \
      || { error "Preprocessing failed. Log: $logfile"; tail -20 "$logfile"; return 1; }
  fi

  printf "\n"
  info "Checking gate: models/embeddings.npy..."
  if gate_2_preprocessing; then
    success "Gate PASSED — embeddings cache found"
    mark_done 2
  else
    error "Gate FAILED — models/embeddings.npy not found"
    warn "$(step_hint 2)"
    return 1
  fi
}

run_step_3() {
  local logfile="$1"
  info "Generating weak labels..."
  if $VERBOSE; then
    (cd "$PROJECT_ROOT" && python3 scripts/generate_weak_labels.py \
      --db historical_reddit_data.db \
      --output data/weak_labels.csv \
      --threshold 0.5 \
      --include-neutral \
      --neutral-threshold 0.1) | tee "$logfile"
  else
    (cd "$PROJECT_ROOT" && python3 scripts/generate_weak_labels.py \
      --db historical_reddit_data.db \
      --output data/weak_labels.csv \
      --threshold 0.5 \
      --include-neutral \
      --neutral-threshold 0.1) > "$logfile" 2>&1 \
      && success "Weak labels written to data/weak_labels.csv" \
      || { error "Weak label generation failed. Log: $logfile"; tail -20 "$logfile"; return 1; }
  fi

  printf "\n"
  info "Checking gate: data/weak_labels.csv ≥ 30,000 rows..."
  if gate_3_weak_labels; then
    local count
    count=$(python3 -c "
import csv
with open('$PROJECT_ROOT/data/weak_labels.csv') as f:
    print(sum(1 for _ in csv.reader(f)) - 1)
")
    success "Gate PASSED — $count labeled rows"
    mark_done 3
  else
    error "Gate FAILED — fewer than 30,000 rows"
    warn "$(step_hint 3)"
    return 1
  fi
}

run_step_4() {
  local logfile="$1"
  info "Training sentiment model (20–40 min on MPS, longer on CPU)..."
  printf "  ${DIM}Logs: $logfile${RESET}\n\n"
  if $VERBOSE; then
    (cd "$PROJECT_ROOT" && python3 - <<'PYEOF'
from src.ml.sentiment import train
result = train(
    weak_labels_path="data/weak_labels.csv",
    model_dir="models/sentiment_v1",
    val_split=0.2,
    epochs=3,
    lr=2e-5,
    batch_size=16,
    max_length=256,
    mlflow_tracking=True,
)
print(f"Val F1 (macro):  {result['val_f1']:.4f}")
print(f"  F1 positive:   {result['val_f1_positive']:.4f}")
print(f"  F1 neutral:    {result['val_f1_neutral']:.4f}")
print(f"  F1 negative:   {result['val_f1_negative']:.4f}")
print(f"Device:          {result['device']}")
print(f"Model saved to:  {result['model_dir']}")
PYEOF
) | tee "$logfile"
  else
    (cd "$PROJECT_ROOT" && python3 - <<'PYEOF'
from src.ml.sentiment import train
result = train(
    weak_labels_path="data/weak_labels.csv",
    model_dir="models/sentiment_v1",
    val_split=0.2,
    epochs=3,
    lr=2e-5,
    batch_size=16,
    max_length=256,
    mlflow_tracking=True,
)
print(f"Val F1 (macro):  {result['val_f1']:.4f}")
print(f"  F1 positive:   {result['val_f1_positive']:.4f}")
print(f"  F1 neutral:    {result['val_f1_neutral']:.4f}")
print(f"  F1 negative:   {result['val_f1_negative']:.4f}")
print(f"Device:          {result['device']}")
print(f"Model saved to:  {result['model_dir']}")
PYEOF
) > "$logfile" 2>&1 \
      && { grep -E "Val F1|F1 (positive|neutral|negative)|Device" "$logfile" | \
           while read -r line; do success "$line"; done; } \
      || { error "Training failed. Log: $logfile"; tail -20 "$logfile"; return 1; }
  fi

  printf "\n"
  info "Checking gate: val_f1 ≥ 0.70..."
  local f1
  f1=$(grep -oP "(?<=Val F1 \(macro\):\s{2})\d+\.\d+" "$logfile" 2>/dev/null || echo "0")
  if gate_4_sentiment_model && python3 -c "exit(0 if float('$f1') >= 0.70 else 1)" 2>/dev/null; then
    success "Gate PASSED — val_f1 = $f1"
    mark_done 4
  elif gate_4_sentiment_model; then
    warn "Model saved but val_f1 = $f1 (below 0.70 target)"
    warn "$(step_hint 4)"
    printf "  Continue anyway? [y/N] "
    read -r ans
    [[ "$ans" =~ ^[Yy]$ ]] && mark_done 4 || return 1
  else
    error "Gate FAILED — model directory not found"
    warn "$(step_hint 4)"
    return 1
  fi
}

run_step_5() {
  local logfile="$1"
  info "Running batch inference across all preprocessed records..."
  if $VERBOSE; then
    (cd "$PROJECT_ROOT" && python3 scripts/batch_inference.py \
      --db historical_reddit_data.db \
      --model-dir models/sentiment_v1 \
      --batch-size 1000) | tee "$logfile"
  else
    (cd "$PROJECT_ROOT" && python3 scripts/batch_inference.py \
      --db historical_reddit_data.db \
      --model-dir models/sentiment_v1 \
      --batch-size 1000) > "$logfile" 2>&1 \
      && success "Batch inference complete" \
      || { error "Batch inference failed. Log: $logfile"; tail -20 "$logfile"; return 1; }
  fi

  printf "\n"
  info "Checking gate: sentiment_predictions table populated..."
  if gate_5_batch_inference; then
    local n
    n=$(python_query "SELECT COUNT(*) FROM sentiment_predictions")
    success "Gate PASSED — $n predictions written"
    mark_done 5
  else
    error "Gate FAILED — sentiment_predictions table is empty or missing"
    warn "$(step_hint 5)"
    return 1
  fi
}

run_step_6() {
  local logfile="$1"
  info "Training BERTopic model (this may take several minutes)..."
  if $VERBOSE; then
    (cd "$PROJECT_ROOT" && python3 scripts/train_topic_model.py \
      --db historical_reddit_data.db \
      --cache-dir models/ \
      --days 90 \
      --min-cluster-size 30 \
      --min-topic-size 30 \
      --nr-topics auto) | tee "$logfile"
  else
    (cd "$PROJECT_ROOT" && python3 scripts/train_topic_model.py \
      --db historical_reddit_data.db \
      --cache-dir models/ \
      --days 90 \
      --min-cluster-size 30 \
      --min-topic-size 30 \
      --nr-topics auto) > "$logfile" 2>&1 \
      && success "Topic modeling complete" \
      || { error "Topic modeling failed. Log: $logfile"; tail -20 "$logfile"; return 1; }
  fi

  printf "\n"
  info "Checking gate: ≥ 20 coherent topics (coherence ≥ 0.50)..."
  if gate_6_topic_modeling; then
    local n
    n=$(python_query "SELECT COUNT(*) FROM topics WHERE coherence_score >= 0.50")
    success "Gate PASSED — $n coherent topics"
    mark_done 6
  else
    local n
    n=$(python_query "SELECT COUNT(*) FROM topics WHERE coherence_score >= 0.50" 2>/dev/null || echo 0)
    error "Gate FAILED — only $n coherent topics found (need ≥ 20)"
    warn "$(step_hint 6)"
    return 1
  fi
}

run_step_7() {
  local logfile="$1"
  info "Running time series analysis and 14-day forecast..."
  if $VERBOSE; then
    (cd "$PROJECT_ROOT" && python3 scripts/run_timeseries.py \
      --db historical_reddit_data.db \
      --days 90 \
      --forecast-days 14) | tee "$logfile"
  else
    (cd "$PROJECT_ROOT" && python3 scripts/run_timeseries.py \
      --db historical_reddit_data.db \
      --days 90 \
      --forecast-days 14) > "$logfile" 2>&1 \
      && success "Time series analysis complete" \
      || { error "Time series failed. Log: $logfile"; tail -20 "$logfile"; return 1; }
  fi

  printf "\n"
  info "Checking gate: sentiment_forecast table populated..."
  if gate_7_timeseries; then
    local n max_date
    n=$(python_query "SELECT COUNT(*) FROM sentiment_forecast")
    max_date=$(python_query "SELECT MAX(date) FROM sentiment_forecast")
    success "Gate PASSED — $n forecast rows, horizon through $max_date"
    mark_done 7
  else
    error "Gate FAILED — sentiment_forecast table is empty or missing"
    warn "$(step_hint 7)"
    return 1
  fi
}

# ── Prompt helper ──────────────────────────────────────────────────────────────

prompt_step() {
  local step="$1"
  local name
  name=$(step_name "$step")

  printf "\n"
  printf "  ${BOLD}Step $step — $name${RESET}\n"
  dim "$(step_desc $step)"
  dim "Gate: $(step_gate_desc $step)"
  printf "\n"
  printf "  [Enter] Run    [s] Skip    [q] Quit  > "
  read -r ans
  case "$ans" in
    s|S) warn "Skipped step $step"; return 2 ;;
    q|Q) info "Exiting."; exit 0 ;;
    *)   return 0 ;;
  esac
}

# ── Modes ──────────────────────────────────────────────────────────────────────

mode_check() {
  header "Pipeline Status"
  if [[ -f "$DB" ]]; then
    print_status_table true
  else
    warn "Database not found at $DB — showing cached status only"
    print_status_table false
  fi
}

mode_interactive() {
  clear 2>/dev/null || true
  printf "\n"
  printf "  ${BOLD}${BLUE}Reddit Analyzer — ML Pipeline${RESET}\n"
  printf "  %s\n" "──────────────────────────────"
  dim "DB: $DB"
  printf "\n"

  if [[ -f "$DB" ]]; then
    print_status_table true
  else
    warn "Database not found at $DB"
    printf "\n"
  fi

  printf "  Run which step? [1-7 / a=all / q=quit]  > "
  read -r ans

  case "$ans" in
    [1-7])
      prompt_step "$ans"
      local rc=$?
      [[ $rc -eq 0 ]] && run_step "$ans"
      ;;
    a|A) mode_all ;;
    q|Q) exit 0 ;;
    *) warn "Unrecognized input: '$ans'"; mode_interactive ;;
  esac
}

mode_step() {
  local step="$1"
  [[ "$step" =~ ^[1-7]$ ]] || die "Invalid step: $step (must be 1–7)"
  header "Pipeline Status"
  print_status_table true
  run_step "$step"
}

mode_all() {
  header "Running full pipeline"
  print_status_table true

  for i in 1 2 3 4 5 6 7; do
    prompt_step "$i"
    local rc=$?
    if [[ $rc -eq 0 ]]; then
      run_step "$i" || {
        error "Step $i failed."
        printf "\n  Continue to next step anyway? [y/N]  > "
        read -r cont
        [[ "$cont" =~ ^[Yy]$ ]] || exit 1
      }
    fi
  done

  printf "\n"
  header "Pipeline complete"
  print_status_table true
}

# ── Argument parsing ───────────────────────────────────────────────────────────

while [[ $# -gt 0 ]]; do
  case "$1" in
    --check)   MODE="check" ;;
    --all)     MODE="all" ;;
    --step)    MODE="step"; TARGET_STEP="${2:-}"; shift ;;
    --step=*)  MODE="step"; TARGET_STEP="${1#--step=}" ;;
    --verbose|-v) VERBOSE=true ;;
    --db)      DB="${2:-}"; shift ;;
    --db=*)    DB="${1#--db=}" ;;
    --help|-h)
      printf "\nUsage: %s [options]\n\n" "$(basename "$0")"
      printf "  --check          Show gate + freshness status for all steps\n"
      printf "  --step N         Run only step N (1–7)\n"
      printf "  --all            Run all steps with confirmation prompts\n"
      printf "  --verbose, -v    Show full command output\n"
      printf "  --db PATH        Override database path (default: historical_reddit_data.db)\n"
      printf "\n"
      exit 0
      ;;
    *) die "Unknown option: $1  (try --help)" ;;
  esac
  shift
done

# ── Entry point ────────────────────────────────────────────────────────────────

cd "$PROJECT_ROOT"

case "$MODE" in
  check)       mode_check ;;
  step)        mode_step "$TARGET_STEP" ;;
  all)         mode_all ;;
  interactive) mode_interactive ;;
esac
