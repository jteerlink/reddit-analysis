#!/usr/bin/env bash
# run_pipeline.sh — Interactive guide for the Reddit Analyzer ML pipeline
#
# Usage:
#   ./scripts/run_pipeline.sh              # run all steps without per-step prompts
#   ./scripts/run_pipeline.sh --interactive  # interactive menu
#   ./scripts/run_pipeline.sh --check      # show status table only
#   ./scripts/run_pipeline.sh --step N     # run a specific step (1-9)
#   ./scripts/run_pipeline.sh step N       # run a specific step (1-9)
#   ./scripts/run_pipeline.sh N            # run a specific step (1-9)
#   ./scripts/run_pipeline.sh --all        # run all steps without per-step prompts
#   ./scripts/run_pipeline.sh --confirm-steps  # ask before each step during all-step runs
#   ./scripts/run_pipeline.sh --no-neon-sync  # skip post-run SQLite→Neon mirror
#   ./scripts/run_pipeline.sh --verbose    # show full command output

set -euo pipefail

# ── Paths ──────────────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DB="${DB_PATH:-${REDDIT_DB_PATH:-$PROJECT_ROOT/historical_reddit_data.db}}"
STATUS_DIR="$PROJECT_ROOT/.pipeline_status"
LOG_DIR="$PROJECT_ROOT/.pipeline_logs"

# Prefer the project venv Python so all ML/enrichment packages are available.
if [[ -x "${PROJECT_ROOT}/.venv/bin/python3" ]]; then
  PYTHON="${PROJECT_ROOT}/.venv/bin/python3"
else
  PYTHON="python3"
fi

# ── Flags ──────────────────────────────────────────────────────────────────────
MODE="all"   # interactive | check | step | all
TARGET_STEP=""
VERBOSE=false
DB_PATH_OVERRIDE=false
NEON_SYNC=true
ENVIRONMENT_READY=false
CONFIRM_STEPS=false

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

trim_value() {
  local value="$1"
  value="${value#"${value%%[![:space:]]*}"}"
  value="${value%"${value##*[![:space:]]}"}"
  printf '%s' "$value"
}

load_dotenv_file() {
  local env_file="$PROJECT_ROOT/.env"
  local line key value

  [[ -f "$env_file" ]] || return 0

  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%$'\r'}"
    line="$(trim_value "$line")"

    [[ -z "$line" || "$line" == \#* ]] && continue
    [[ "$line" == export\ * ]] && line="${line#export }"

    if [[ "$line" =~ ^([A-Za-z_][A-Za-z0-9_]*)=(.*)$ ]]; then
      key="${BASH_REMATCH[1]}"
      value="$(trim_value "${BASH_REMATCH[2]}")"

      if [[ "$value" == \"*\" && "$value" == *\" ]]; then
        value="${value:1:${#value}-2}"
      elif [[ "$value" == \'*\' && "$value" == *\' ]]; then
        value="${value:1:${#value}-2}"
      fi

      if [[ -z "${!key+x}" ]]; then
        export "${key}=${value}"
      fi
    fi
  done < "$env_file"
}

refresh_python() {
  if [[ -x "${PROJECT_ROOT}/.venv/bin/python3" ]]; then
    PYTHON="${PROJECT_ROOT}/.venv/bin/python3"
  elif [[ -x "${PROJECT_ROOT}/.venv/bin/python" ]]; then
    PYTHON="${PROJECT_ROOT}/.venv/bin/python"
  elif [[ -z "${PYTHON:-}" ]]; then
    PYTHON="python3"
  fi
}

configure_database_environment() {
  if [[ "$DB_PATH_OVERRIDE" != "true" ]]; then
    if [[ -n "${DB_PATH:-}" ]]; then
      DB="$DB_PATH"
    elif [[ -n "${REDDIT_DB_PATH:-}" ]]; then
      DB="$REDDIT_DB_PATH"
    fi
  fi

  if [[ "$DB" != postgres://* && "$DB" != postgresql://* && "$DB" != /* ]]; then
    DB="$PROJECT_ROOT/$DB"
  fi

  if [[ -z "${DATABASE_URL:-}" && "$DB" != postgres://* && "$DB" != postgresql://* ]]; then
    export REDDIT_DB_PATH="$DB"
    export DATABASE_PATH="$DB"
  fi
}

run_environment_command() {
  local logfile="$1"
  local label="$2"
  shift 2

  info "$label..."
  if $VERBOSE; then
    if (cd "$PROJECT_ROOT" && "$@") 2>&1 | tee -a "$logfile"; then
      success "$label complete"
    else
      local rc=$?
      error "$label failed. Log: $logfile"
      return "$rc"
    fi
  else
    if (cd "$PROJECT_ROOT" && "$@") >> "$logfile" 2>&1; then
      success "$label complete"
    else
      local rc=$?
      error "$label failed. Log: $logfile"
      tail -20 "$logfile"
      return "$rc"
    fi
  fi
}

run_step_6_7_dependency_check() {
  (cd "$PROJECT_ROOT" && "$PYTHON" - <<'PYEOF'
from importlib.metadata import version

import bertopic
import cmdstanpy
import regex
import ruptures
import transformers
from prophet import Prophet


def version_tuple(value: str) -> tuple[int, ...]:
    return tuple(int(part) for part in value.split(".")[:3])


regex_version = version("regex")
if version_tuple(regex_version) < (2025, 10, 22):
    raise RuntimeError(
        f"regex>={'.'.join(map(str, (2025, 10, 22)))} is required; found {regex_version}"
    )

print(f"regex=={regex_version}")
print(f"transformers=={version('transformers')}")
print(f"bertopic=={version('bertopic')}")
print(f"prophet=={version('prophet')}")
print(f"cmdstanpy=={version('cmdstanpy')}")
print(f"ruptures=={version('ruptures')}")
print("Pipeline dependency imports verified")
PYEOF
  )
}

verify_pipeline_dependencies() {
  local logfile="$1"

  info "Verifying step 6/7 dependency imports..."
  if $VERBOSE; then
    if run_step_6_7_dependency_check 2>&1 | tee -a "$logfile"; then
      success "Step 6/7 dependency imports verified"
    else
      local rc=$?
      error "Pipeline dependency import check failed. Log: $logfile"
      return "$rc"
    fi
  else
    if run_step_6_7_dependency_check >> "$logfile" 2>&1; then
      success "Step 6/7 dependency imports verified"
    else
      local rc=$?
      error "Pipeline dependency import check failed. Log: $logfile"
      tail -40 "$logfile"
      return "$rc"
    fi
  fi
}

ensure_pipeline_environment() {
  local step="${1:-unknown}"

  [[ "$ENVIRONMENT_READY" == "true" ]] && return 0

  mkdir -p "$LOG_DIR" "$STATUS_DIR" "$PROJECT_ROOT/models" "$PROJECT_ROOT/data"
  configure_database_environment
  export PYTHONPATH="$PROJECT_ROOT${PYTHONPATH:+:$PYTHONPATH}"

  local logfile="$LOG_DIR/environment_setup_$(date +%Y%m%d_%H%M%S).log"
  header "Preparing pipeline environment"
  if [[ "$step" =~ ^[1-9]$ ]]; then
    dim "Before step $step — $(step_name "$step")"
  else
    dim "At script startup"
  fi
  dim "Log: $logfile"
  printf "\n"

  if command -v uv >/dev/null 2>&1; then
    if [[ ! -d "$PROJECT_ROOT/.venv" ]]; then
      run_environment_command "$logfile" "Creating uv virtual environment" uv venv || return 1
    fi
    refresh_python
    run_environment_command "$logfile" "Installing ml + production dependencies" \
      uv pip install --python "$PYTHON" -e ".[ml,production]" || return 1
    refresh_python
  else
    refresh_python
    "$PYTHON" -m pip --version >/dev/null 2>&1 \
      || die "uv is not installed and $PYTHON cannot run pip"
    run_environment_command "$logfile" "Installing ml + production dependencies with pip" \
      "$PYTHON" -m pip install -e ".[ml,production]" || return 1
  fi

  verify_pipeline_dependencies "$logfile" || return 1
  require_db
  success "Environment ready: $($PYTHON --version 2>&1)"
  ENVIRONMENT_READY=true
  printf "\n"
}

require_db() {
  [[ -n "${DATABASE_URL:-}" ]] && return 0
  [[ -f "$DB" ]] || die "Database not found: $DB\n  Set DB_PATH or run from project root."
}

extract_val_f1() {
  local logfile="$1"

  awk -F: '
    /Val F1 \(macro\)/ {
      value = $2
      gsub(/^[[:space:]]+|[[:space:]]+$/, "", value)
      if (value ~ /^[0-9]+([.][0-9]+)?$/) {
        print value
        exit
      }
    }
  ' "$logfile"
}

sync_neon() {
  local context="${1:-pipeline}"

  if [[ "$NEON_SYNC" != "true" ]]; then
    dim "Neon mirror skipped for $context (--no-neon-sync)"
    return 0
  fi

  if [[ -n "${DATABASE_URL:-}" ]]; then
    dim "Neon mirror skipped for $context (pipeline is already using DATABASE_URL)"
    return 0
  fi

  if [[ "$DB" == postgres://* || "$DB" == postgresql://* ]]; then
    dim "Neon mirror skipped for $context (DB path is already PostgreSQL)"
    return 0
  fi

  if [[ ! -f "$DB" ]]; then
    warn "Neon mirror skipped for $context — SQLite source not found: $DB"
    return 0
  fi

  info "Mirroring SQLite to Neon after $context..."
  if "$PYTHON" - <<PYEOF
import os
from argparse import Namespace
from pathlib import Path

from dotenv import load_dotenv
from scripts import migrate_to_neon

load_dotenv(dotenv_path=Path("$PROJECT_ROOT") / ".env")
database_url = os.environ.get("NEON_DATABASE_URL") or os.environ.get("DATABASE_URL")
if not database_url:
    print("SKIP missing NEON_DATABASE_URL or DATABASE_URL in .env")
    raise SystemExit(0)

source = Path("$DB")
args = Namespace(
    source=str(source),
    database_url=database_url,
    schema=str(migrate_to_neon.SCHEMA_PATH),
    seed=str(migrate_to_neon.SEED_PATH),
    batch_size=int(os.environ.get("NEON_MIRROR_BATCH_SIZE", "1000")),
    create_schema=os.environ.get("NEON_MIRROR_CREATE_SCHEMA", "true").lower()
    not in {"0", "false", "no"},
    dry_run=False,
)
raise SystemExit(migrate_to_neon.run(args))
PYEOF
  then
    success "Neon mirror complete for $context"
  else
    local rc=$?
    error "Neon mirror failed for $context"
    return "$rc"
  fi
}

python_query() {
  # Run a DB query via Python; returns stdout trimmed
  "$PYTHON" - <<EOF
import os, sqlite3, sys
try:
    if os.environ.get("DATABASE_URL"):
        import psycopg2
        conn = psycopg2.connect(os.environ["DATABASE_URL"])
        cur = conn.cursor()
        cur.execute("""$1""")
        result = cur.fetchone()
    else:
        conn = sqlite3.connect('$DB')
        result = conn.execute("""$1""").fetchone()
    print(result[0] if result and result[0] is not None else 0)
except Exception as e:
    print(0)
EOF
}

table_exists() {
  "$PYTHON" - <<EOF
import os, sqlite3
try:
    if os.environ.get("DATABASE_URL"):
        import psycopg2
        conn = psycopg2.connect(os.environ["DATABASE_URL"])
        r = conn.cursor()
        r.execute("SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename=%s", ('$1',))
        row = r.fetchone()
    else:
        conn = sqlite3.connect('$DB')
        row = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", ('$1',)).fetchone()
    print("yes" if row else "no")
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
  if [[ -n "${DATABASE_URL:-}" ]]; then
    "$PYTHON" -c "import psycopg2" 2>/dev/null || return 1
    return 0
  fi
  "$PYTHON" -c "import sqlite3" 2>/dev/null || return 1
  [[ -f "$DB" ]] || return 1
  return 0
}

gate_2_preprocessing() {
  # Gate: embeddings cache exists
  [[ -f "$PROJECT_ROOT/models/embeddings_cache.npy" ]] || return 1
  return 0
}

gate_3_weak_labels() {
  # Gate: weak_labels.csv exists with >=30k rows
  local csv="$PROJECT_ROOT/data/weak_labels.csv"
  [[ -f "$csv" ]] || return 1
  local count
  count=$("$PYTHON" -c "
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

gate_8_analysis_artifacts() {
  # Gate: at least one succeeded analysis artifact
  [[ "$(table_exists analysis_artifacts)" == "yes" ]] || return 1
  local n
  n=$(python_query "SELECT COUNT(*) FROM analysis_artifacts WHERE status = 'succeeded'")
  [[ "$n" -gt 0 ]] || return 1
  return 0
}

gate_9_llm_enrichment() {
  # Gate: at least one succeeded Ollama artifact
  [[ "$(table_exists analysis_artifacts)" == "yes" ]] || return 1
  local n
  n=$(python_query "SELECT COUNT(*) FROM analysis_artifacts WHERE status = 'succeeded' AND provider = 'ollama'")
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
    8) gate_8_analysis_artifacts ;;
    9) gate_9_llm_enrichment ;;
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
  csv_mtime=$("$PYTHON" -c "import os; print(int(os.path.getmtime('$csv')))" 2>/dev/null || echo 0)
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
  model_mtime=$("$PYTHON" -c "import os; print(int(os.path.getmtime('$model_dir')))" 2>/dev/null || echo 0)
  csv_mtime=$("$PYTHON" -c "import os; print(int(os.path.getmtime('$csv')))" 2>/dev/null || echo 0)
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
    model_mtime=$("$PYTHON" -c "import os; print(int(os.path.getmtime('$model_file')))" 2>/dev/null || echo 0)
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
  today=$("$PYTHON" -c "from datetime import date; print(date.today())")
  if [[ -z "$max_date" || "$max_date" == "0" ]]; then
    echo "—"
  elif [[ "$max_date" < "$today" ]]; then
    printf "${YELLOW}STALE${RESET}  (forecast ends %s, today is %s)" "$max_date" "$today"
  else
    printf "${GREEN}Fresh${RESET}"
  fi
}

freshness_8_analysis_artifacts() {
  [[ "$(table_exists analysis_artifacts)" == "yes" ]] || { echo "—"; return; }
  local n
  n=$(python_query "SELECT COUNT(*) FROM analysis_artifacts WHERE status = 'succeeded'" 2>/dev/null || echo 0)
  if [[ "$n" -gt 0 ]]; then
    printf "${GREEN}Fresh${RESET}  (%s artifacts)" "$n"
  else
    echo "—"
  fi
}

freshness_9_llm_enrichment() {
  [[ "$(table_exists analysis_artifacts)" == "yes" ]] || { echo "—"; return; }
  local n
  n=$(python_query "SELECT COUNT(*) FROM analysis_artifacts WHERE status = 'succeeded' AND provider = 'ollama'" 2>/dev/null || echo 0)
  if [[ "$n" -gt 0 ]]; then
    printf "${GREEN}Fresh${RESET}  (%s ollama artifacts)" "$n"
  else
    echo "—"
  fi
}

get_freshness() {
  local step="${1:-}"
  case "$step" in
    1) echo "—" ;;
    2) freshness_2_preprocessing ;;
    3) freshness_3_weak_labels ;;
    4) freshness_4_sentiment_model ;;
    5) freshness_5_batch_inference ;;
    6) freshness_6_topic_modeling ;;
    7) freshness_7_timeseries ;;
    8) freshness_8_analysis_artifacts ;;
    9) freshness_9_llm_enrichment ;;
  esac
}

# ── Step metadata ──────────────────────────────────────────────────────────────

step_name() {
  local step="${1:-}"
  case "$step" in
    1) echo "Prerequisites" ;;
    2) echo "Preprocessing" ;;
    3) echo "Weak Labels" ;;
    4) echo "Train Sentiment Model" ;;
    5) echo "Batch Inference" ;;
    6) echo "Topic Modeling" ;;
    7) echo "Time Series & Forecasting" ;;
    8) echo "Analysis Artifacts" ;;
    9) echo "LLM Enrichment" ;;
  esac
}

step_desc() {
  local step="${1:-}"
  case "$step" in
    1) echo "Install ml+production deps, verify database, create models/ and data/ dirs" ;;
    2) echo "Clean raw posts/comments, generate sentence embeddings, write preprocessed table" ;;
    3) echo "Score preprocessed text with keyword rules and produce a labeled training CSV" ;;
    4) echo "Fine-tune DistilBERT on weak labels (~20-40 min on MPS/GPU)" ;;
    5) echo "Run the trained sentiment model across all preprocessed records" ;;
    6) echo "Discover dominant themes with BERTopic and track them week over week" ;;
    7) echo "Aggregate daily sentiment, detect trend shifts, generate 14-day Prophet forecasts" ;;
    8) echo "Backfill dashboard intelligence artifacts (narrative events, briefs, trend analysis)" ;;
    9) echo "Ollama LLM enrichment: narrative summaries, thread analysis, analyst brief, topic labels" ;;
  esac
}

step_gate_desc() {
  local step="${1:-}"
  case "$step" in
    1) echo "project Python reachable, database exists, models/ and data/ present" ;;
    2) echo "models/embeddings_cache.npy exists" ;;
    3) echo "data/weak_labels.csv exists with ≥ 30,000 rows" ;;
    4) echo "models/sentiment_v1/config.json exists" ;;
    5) echo "sentiment_predictions table has rows" ;;
    6) echo "≥ 20 topics with coherence ≥ 0.50 in topics table" ;;
    7) echo "sentiment_forecast table has rows" ;;
    8) echo "analysis_artifacts table has ≥ 1 succeeded artifact" ;;
    9) echo "analysis_artifacts table has ≥ 1 succeeded artifact with provider='ollama'" ;;
  esac
}

step_hint() {
  local step="${1:-}"
  case "$step" in
    2) echo "Run: uv pip install -e \".[ml,production]\"  |  Check DB path with: ls -lh $DB" ;;
    3) echo "Lower --threshold to 0.4 in the weak labels step to get more labeled rows" ;;
    4) echo "Lower --threshold 0.4 in weak labels step or check models/sentiment_v1/ for partial output" ;;
    5) echo "Reduce --batch-size to 8 if OOM on training; use --batch-size 512 for inference" ;;
    6) echo "Try: TOPIC_MIN_CLUSTER_SIZE=15 TOPIC_MIN_TOPIC_SIZE=15 ./scripts/run_pipeline.sh --step 6" ;;
    7) echo "Ensure batch inference ran first to populate sentiment_predictions" ;;
    8) echo "Ensure steps 1–7 completed; check logs in .pipeline_logs/" ;;
    9) echo "Set OLLAMA_API_KEY in .env and ensure Ollama is running at OLLAMA_BASE_URL" ;;
    *) echo "" ;;
  esac
}

# ── Status table ───────────────────────────────────────────────────────────────

print_status_table() {
  local check_db="${1:-true}"
  printf "\n"
  printf "  ${BOLD}%-3s  %-28s  %-6s  %-10s  %s${RESET}\n" "#" "Step" "Gate" "Last Run" "Freshness"
  printf "  %s\n" "──────────────────────────────────────────────────────────────────────────────"

  for i in 1 2 3 4 5 6 7 8 9; do
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
  local step="${1:-}"
  local sync_after="${2:-true}"
  [[ "$step" =~ ^[1-9]$ ]] || die "Invalid step: ${step:-<empty>} (must be 1–9)"
  local name
  name=$(step_name "$step")

  header "Step $step — $name"
  dim "$(step_desc $step)"
  printf "\n"

  mkdir -p "$LOG_DIR"
  local logfile="$LOG_DIR/step_${step}_$(date +%Y%m%d_%H%M%S).log"

  ensure_pipeline_environment "$step"

  case "$step" in
    1) run_step_1 "$logfile" ;;
    2) run_step_2 "$logfile" ;;
    3) run_step_3 "$logfile" ;;
    4) run_step_4 "$logfile" ;;
    5) run_step_5 "$logfile" ;;
    6) run_step_6 "$logfile" ;;
    7) run_step_7 "$logfile" ;;
    8) run_step_8 "$logfile" ;;
    9) run_step_9 "$logfile" ;;
  esac

  if [[ "$sync_after" == "true" ]]; then
    sync_neon "step $step"
  fi
}

run_step_1() {
  local logfile="$1"
  info "Recording prepared environment details..."
  {
    printf 'Python: %s\n' "$PYTHON"
    "$PYTHON" --version
    if command -v uv >/dev/null 2>&1; then
      uv --version
    fi
    if [[ -n "${DATABASE_URL:-}" ]]; then
      printf 'Database: DATABASE_URL configured\n'
    else
      printf 'Database: %s\n' "$DB"
    fi
    printf 'PYTHONPATH: %s\n' "${PYTHONPATH:-}"
  } > "$logfile" 2>&1
  success "Dependencies installed and environment ready"

  info "Verifying database..."
  if [[ -n "${DATABASE_URL:-}" ]]; then
    success "Database configured through DATABASE_URL"
  else
    [[ -f "$DB" ]] && success "Database found: $(du -sh "$DB" | cut -f1) — $DB" \
      || { error "Database not found at $DB"; return 1; }
  fi

  info "Creating models/ and data/ directories..."
  mkdir -p "$PROJECT_ROOT/models" "$PROJECT_ROOT/data"
  success "Directories ready"

  mark_done 1
}

run_step_2() {
  local logfile="$1"
  info "Running preprocessing (this may take several minutes)..."
  if $VERBOSE; then
    (cd "$PROJECT_ROOT" && REDDIT_PIPELINE_DB="$DB" "$PYTHON" - <<'PYEOF'
import os
from src.ml.preprocessing import run_preprocessing
result = run_preprocessing(
    db_path=os.environ["REDDIT_PIPELINE_DB"],
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
    (cd "$PROJECT_ROOT" && REDDIT_PIPELINE_DB="$DB" "$PYTHON" - <<'PYEOF'
import os
from src.ml.preprocessing import run_preprocessing
result = run_preprocessing(
    db_path=os.environ["REDDIT_PIPELINE_DB"],
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
  info "Checking gate: models/embeddings_cache.npy..."
  if gate_2_preprocessing; then
    success "Gate PASSED — embeddings cache found"
    mark_done 2
  else
    error "Gate FAILED — models/embeddings_cache.npy not found"
    warn "$(step_hint 2)"
    return 1
  fi
}

run_step_3() {
  local logfile="$1"
  info "Generating weak labels..."
  if $VERBOSE; then
    (cd "$PROJECT_ROOT" && "$PYTHON" scripts/generate_weak_labels.py \
      --db "$DB" \
      --output data/weak_labels.csv \
      --threshold 0.5 \
      --include-neutral \
      --neutral-threshold 0.1) | tee "$logfile"
  else
    (cd "$PROJECT_ROOT" && "$PYTHON" scripts/generate_weak_labels.py \
      --db "$DB" \
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
    count=$("$PYTHON" -c "
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
    (cd "$PROJECT_ROOT" && "$PYTHON" - <<'PYEOF'
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
    (cd "$PROJECT_ROOT" && "$PYTHON" - <<'PYEOF'
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
  f1=$(extract_val_f1 "$logfile")
  f1="${f1:-0}"
  if gate_4_sentiment_model && "$PYTHON" -c "exit(0 if float('$f1') >= 0.70 else 1)" 2>/dev/null; then
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
    (cd "$PROJECT_ROOT" && "$PYTHON" scripts/batch_inference.py \
      --db "$DB" \
      --model-dir models/sentiment_v1 \
      --batch-size 1000) | tee "$logfile"
  else
    (cd "$PROJECT_ROOT" && "$PYTHON" scripts/batch_inference.py \
      --db "$DB" \
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
  local topic_days="${TOPIC_DAYS:-90}"
  local topic_min_cluster_size="${TOPIC_MIN_CLUSTER_SIZE:-30}"
  local topic_min_topic_size="${TOPIC_MIN_TOPIC_SIZE:-30}"
  local topic_n_neighbors="${TOPIC_N_NEIGHBORS:-15}"
  local topic_n_components="${TOPIC_N_COMPONENTS:-5}"
  local topic_nr_topics="${TOPIC_NR_TOPICS:-auto}"

  info "Training BERTopic model (this may take several minutes)..."
  dim "Topic params: days=$topic_days min_cluster_size=$topic_min_cluster_size min_topic_size=$topic_min_topic_size n_neighbors=$topic_n_neighbors n_components=$topic_n_components nr_topics=$topic_nr_topics"
  if $VERBOSE; then
    (cd "$PROJECT_ROOT" && "$PYTHON" scripts/train_topic_model.py \
      --db "$DB" \
      --cache-dir models/ \
      --days "$topic_days" \
      --min-cluster-size "$topic_min_cluster_size" \
      --min-topic-size "$topic_min_topic_size" \
      --n-neighbors "$topic_n_neighbors" \
      --n-components "$topic_n_components" \
      --nr-topics "$topic_nr_topics" \
      --skip-gate) | tee "$logfile"
  else
    (cd "$PROJECT_ROOT" && "$PYTHON" scripts/train_topic_model.py \
      --db "$DB" \
      --cache-dir models/ \
      --days "$topic_days" \
      --min-cluster-size "$topic_min_cluster_size" \
      --min-topic-size "$topic_min_topic_size" \
      --n-neighbors "$topic_n_neighbors" \
      --n-components "$topic_n_components" \
      --nr-topics "$topic_nr_topics" \
      --skip-gate) > "$logfile" 2>&1 \
      && success "Topic modeling complete" \
      || { error "Topic modeling crashed. Log: $logfile"; tail -20 "$logfile"; return 1; }
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
    error "Gate FAILED — model completed, but only $n coherent topics found (need ≥ 20)"
    warn "$(step_hint 6)"
    return 1
  fi
}

run_step_7() {
  local logfile="$1"
  info "Running time series analysis and 14-day forecast..."
  if $VERBOSE; then
    (cd "$PROJECT_ROOT" && "$PYTHON" scripts/run_timeseries.py \
      --db "$DB" \
      --days 90 \
      --forecast-days 14) | tee "$logfile"
  else
    (cd "$PROJECT_ROOT" && "$PYTHON" scripts/run_timeseries.py \
      --db "$DB" \
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

run_step_8() {
  local logfile="$1"
  info "Running analysis artifact backfill..."
  if $VERBOSE; then
    (cd "$PROJECT_ROOT" && "$PYTHON" scripts/run_analysis_jobs.py --db "$DB") | tee "$logfile"
  else
    (cd "$PROJECT_ROOT" && "$PYTHON" scripts/run_analysis_jobs.py --db "$DB") > "$logfile" 2>&1 \
      && success "Analysis artifacts generated" \
      || { error "Analysis artifact jobs failed. Log: $logfile"; tail -20 "$logfile"; return 1; }
  fi

  printf "\n"
  info "Checking gate: analysis_artifacts table has succeeded rows..."
  if gate_8_analysis_artifacts; then
    local n
    n=$(python_query "SELECT COUNT(*) FROM analysis_artifacts WHERE status = 'succeeded'")
    success "Gate PASSED — $n succeeded artifacts"
    mark_done 8
  else
    error "Gate FAILED — no succeeded artifacts found"
    warn "$(step_hint 8)"
    return 1
  fi
}

run_step_9() {
  local logfile="$1"
  info "Running LLM enrichment via Ollama..."
  dim "Requires OLLAMA_API_KEY and OLLAMA_BASE_URL in .env or environment"
  if $VERBOSE; then
    (cd "$PROJECT_ROOT" && "$PYTHON" scripts/run_enrichment.py --db "$DB" --all) | tee "$logfile"
  else
    (cd "$PROJECT_ROOT" && "$PYTHON" scripts/run_enrichment.py --db "$DB" --all) > "$logfile" 2>&1 \
      && success "LLM enrichment complete" \
      || { error "LLM enrichment failed. Log: $logfile"; tail -20 "$logfile"; return 1; }
  fi

  printf "\n"
  info "Checking gate: Ollama artifacts written..."
  if gate_9_llm_enrichment; then
    local n
    n=$(python_query "SELECT COUNT(*) FROM analysis_artifacts WHERE status = 'succeeded' AND provider = 'ollama'")
    success "Gate PASSED — $n Ollama artifacts"
    mark_done 9
  else
    error "Gate FAILED — no succeeded Ollama artifacts found"
    warn "$(step_hint 9)"
    return 1
  fi
}

# ── Prompt helper ──────────────────────────────────────────────────────────────

prompt_step() {
  local step="${1:-}"
  [[ "$step" =~ ^[1-9]$ ]] || die "Invalid step: ${step:-<empty>} (must be 1–9)"
  local name
  local ans
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

  printf "  Run which step? [1-9 / a=all / q=quit]  > "
  read -r ans

  case "$ans" in
    [1-9])
      if prompt_step "$ans"; then
        run_step "$ans" true
      else
        local rc=$?
        [[ $rc -eq 2 ]] || return "$rc"
      fi
      ;;
    a|A) mode_all ;;
    q|Q) exit 0 ;;
    *) warn "Unrecognized input: '$ans'"; mode_interactive ;;
  esac
}

mode_step() {
  local step="${1:-}"
  [[ "$step" =~ ^[1-9]$ ]] || die "Invalid step: ${step:-<empty>} (must be 1–9)"
  header "Selected Pipeline Step"
  dim "DB: $DB"
  printf "\n"
  if check_gate "$step" 2>/dev/null; then
    success "Current gate already passes: step $step — $(step_name "$step")"
  else
    warn "Current gate does not pass yet: step $step — $(step_name "$step")"
  fi
  run_step "$step" true
}

mode_all() {
  header "Running full pipeline"
  print_status_table true

  for i in 1 2 3 4 5 6 7 8 9; do
    if [[ "$CONFIRM_STEPS" == "true" ]]; then
      if prompt_step "$i"; then
        :
      else
        local rc=$?
        [[ "$rc" -eq 2 ]] && continue
        return "$rc"
      fi
    fi

    run_step "$i" false || {
      error "Step $i failed."
      if [[ "$CONFIRM_STEPS" == "true" ]]; then
        printf "\n  Continue to next step anyway? [y/N]  > "
        read -r cont
        [[ "$cont" =~ ^[Yy]$ ]] || exit 1
      else
        exit 1
      fi
    }
  done

  printf "\n"
  sync_neon "full pipeline"
  printf "\n"
  header "Pipeline complete"
  print_status_table true
}

# ── Argument parsing ───────────────────────────────────────────────────────────

while [[ $# -gt 0 ]]; do
  case "$1" in
    [1-9])    MODE="step"; TARGET_STEP="$1" ;;
    step)     MODE="step"; TARGET_STEP="${2:-}"; shift ;;
    --check)   MODE="check" ;;
    --all)     MODE="all" ;;
    --interactive) MODE="interactive" ;;
    --confirm-steps) CONFIRM_STEPS=true ;;
    --step)    MODE="step"; TARGET_STEP="${2:-}"; shift ;;
    --step=*)  MODE="step"; TARGET_STEP="${1#--step=}" ;;
    --no-neon-sync) NEON_SYNC=false ;;
    --verbose|-v) VERBOSE=true ;;
    --db)      DB="${2:-}"; DB_PATH_OVERRIDE=true; shift ;;
    --db=*)    DB="${1#--db=}"; DB_PATH_OVERRIDE=true ;;
    --help|-h)
      printf "\nUsage: %s [options]\n\n" "$(basename "$0")"
      printf "  (no args)        Run all steps without per-step prompts\n"
      printf "  --check          Show gate + freshness status for all steps\n"
      printf "  --step N         Run only step N (1–9)\n"
      printf "  step N           Run only step N (1–9)\n"
      printf "  N                Run only step N (1–9)\n"
      printf "  --all            Run all steps without per-step prompts\n"
      printf "  --interactive    Show interactive menu instead of default all-step run\n"
      printf "  --confirm-steps  Ask before each step during all-step runs\n"
      printf "  --no-neon-sync   Skip post-step/post-run SQLite→Neon mirror\n"
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
load_dotenv_file
configure_database_environment
refresh_python
if [[ "$MODE" != "check" ]]; then
  ensure_pipeline_environment "startup"
fi

case "$MODE" in
  check)       mode_check ;;
  step)        mode_step "$TARGET_STEP" ;;
  all)         mode_all ;;
  interactive) mode_interactive ;;
esac
