#!/usr/bin/env bash
# Start the local FastAPI backend and Next.js dashboard frontend.
#
# Usage:
#   ./scripts/startup.sh
#
# Optional environment overrides:
#   BACKEND_HOST=localhost BACKEND_PORT=8000 FRONTEND_HOST=localhost FRONTEND_PORT=3000 ./scripts/startup.sh
#   START_STREAMLIT=1 STREAMLIT_PORT=8501 ./scripts/startup.sh

set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
DASHBOARD_DIR="${ROOT_DIR}/dashboard"
STATUS_DIR="$(mktemp -d)"

BACKEND_HOST="${BACKEND_HOST:-localhost}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_HOST="${FRONTEND_HOST:-localhost}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"
STREAMLIT_HOST="${STREAMLIT_HOST:-localhost}"
STREAMLIT_PORT="${STREAMLIT_PORT:-8501}"
START_STREAMLIT="${START_STREAMLIT:-0}"
NEXT_PUBLIC_API_BASE_URL="${NEXT_PUBLIC_API_BASE_URL:-http://${BACKEND_HOST}:${BACKEND_PORT}}"

PIDS=()
NAMES=()

die() {
  echo "❌ $*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || die "Missing required command: $1"
}

trim_value() {
  local value="$1"
  value="${value#"${value%%[![:space:]]*}"}"
  value="${value%"${value##*[![:space:]]}"}"
  printf '%s' "${value}"
}

load_dotenv_file() {
  local env_file="${ROOT_DIR}/.env"
  local line key value

  [[ -f "${env_file}" ]] || return 0

  while IFS= read -r line || [[ -n "${line}" ]]; do
    line="${line%$'\r'}"
    line="$(trim_value "${line}")"

    [[ -z "${line}" || "${line}" == \#* ]] && continue
    [[ "${line}" == export\ * ]] && line="${line#export }"

    if [[ "${line}" =~ ^([A-Za-z_][A-Za-z0-9_]*)=(.*)$ ]]; then
      key="${BASH_REMATCH[1]}"
      value="$(trim_value "${BASH_REMATCH[2]}")"

      if [[ "${value}" == \"*\" && "${value}" == *\" ]]; then
        value="${value:1:${#value}-2}"
      elif [[ "${value}" == \'*\' && "${value}" == *\' ]]; then
        value="${value:1:${#value}-2}"
      fi

      if [[ -z "${!key+x}" ]]; then
        export "${key}=${value}"
      fi
    fi
  done < "${env_file}"
}

configure_default_database() {
  local configured_path resolved_path

  [[ -n "${DATABASE_URL:-}" || -n "${REDDIT_DB_PATH:-}" ]] && return 0

  configured_path="${DATABASE_PATH:-}"
  if [[ -n "${configured_path}" ]]; then
    resolved_path="${configured_path}"
    [[ "${resolved_path}" = /* ]] || resolved_path="${ROOT_DIR}/${resolved_path}"
    [[ -f "${resolved_path}" ]] && return 0
  fi

  if [[ -f "${ROOT_DIR}/historical_reddit_data.db" ]]; then
    export REDDIT_DB_PATH="${ROOT_DIR}/historical_reddit_data.db"
  fi
}

port_in_use() {
  local port="$1"
  lsof -nP -iTCP:"${port}" -sTCP:LISTEN >/dev/null 2>&1
}

check_port() {
  local name="$1"
  local port="$2"

  if port_in_use "${port}"; then
    die "${name} port ${port} is already in use. Override the port or stop the existing process."
  fi
}

kill_tree() {
  local pid="$1"
  local child

  for child in $(pgrep -P "${pid}" 2>/dev/null || true); do
    kill_tree "${child}"
  done

  kill "${pid}" >/dev/null 2>&1 || true
}

cleanup() {
  local status=$?

  trap - EXIT INT TERM

  if ((${#PIDS[@]} > 0)); then
    echo
    echo "🛑 Shutting down dashboard services..."
    for pid in "${PIDS[@]}"; do
      kill_tree "${pid}"
    done
    for pid in "${PIDS[@]}"; do
      wait "${pid}" 2>/dev/null || true
    done
  fi

  rm -rf "${STATUS_DIR}"
  exit "${status}"
}

trap cleanup EXIT INT TERM

start_service() {
  local name="$1"
  shift

  echo "▶️  Starting ${name}..."
  (
    cd "${ROOT_DIR}"
    set +e
    "$@"
    code=$?
    set -e
    printf '%s:%s\n' "${name}" "${code}" > "${STATUS_DIR}/${name}.status"
    exit "${code}"
  ) &

  PIDS+=("$!")
  NAMES+=("${name}")
}

monitor_services() {
  local status_file
  local name
  local code

  while true; do
    for status_file in "${STATUS_DIR}"/*.status; do
      [[ -e "${status_file}" ]] || continue
      IFS=: read -r name code < "${status_file}"
      echo "❌ ${name} exited with status ${code}; stopping remaining services."
      exit "${code}"
    done
    sleep 1
  done
}

[[ -d "${DASHBOARD_DIR}" ]] || die "Dashboard directory not found: ${DASHBOARD_DIR}"
[[ -f "${DASHBOARD_DIR}/package.json" ]] || die "Missing dashboard/package.json"

require_command npm
require_command lsof
require_command pgrep

if [[ ! -d "${DASHBOARD_DIR}/node_modules" ]]; then
  die "Missing dashboard/node_modules. Run: cd dashboard && npm install"
fi

load_dotenv_file
configure_default_database

if command -v uv >/dev/null 2>&1; then
  BACKEND_CMD=(uv run --frozen --extra production uvicorn src.api.app:app --reload --host "${BACKEND_HOST}" --port "${BACKEND_PORT}")
  STREAMLIT_CMD=(uv run --frozen --extra production streamlit run app.py --server.address "${STREAMLIT_HOST}" --server.port "${STREAMLIT_PORT}")
else
  if [[ -z "${PYTHON_BIN:-}" ]]; then
    if [[ -x "${ROOT_DIR}/.venv/bin/python" ]]; then
      PYTHON_BIN="${ROOT_DIR}/.venv/bin/python"
    else
      PYTHON_BIN="python3"
    fi
  fi
  require_command "${PYTHON_BIN}"
  BACKEND_CMD=("${PYTHON_BIN}" -m uvicorn src.api.app:app --reload --host "${BACKEND_HOST}" --port "${BACKEND_PORT}")
  STREAMLIT_CMD=("${PYTHON_BIN}" -m streamlit run app.py --server.address "${STREAMLIT_HOST}" --server.port "${STREAMLIT_PORT}")
fi

FRONTEND_CMD=(env "NEXT_PUBLIC_API_BASE_URL=${NEXT_PUBLIC_API_BASE_URL}" npm --prefix "${DASHBOARD_DIR}" run dev -- --hostname "${FRONTEND_HOST}" --port "${FRONTEND_PORT}")

check_port "Backend" "${BACKEND_PORT}"
check_port "Next.js frontend" "${FRONTEND_PORT}"
if [[ "${START_STREAMLIT}" == "1" || "${START_STREAMLIT}" == "true" || "${START_STREAMLIT}" == "yes" ]]; then
  check_port "Streamlit frontend" "${STREAMLIT_PORT}"
fi

echo "🚀 Reddit Analyzer dashboard startup"
echo "   Backend:          http://${BACKEND_HOST}:${BACKEND_PORT}"
echo "   Next.js frontend: http://${FRONTEND_HOST}:${FRONTEND_PORT}"
echo "   API base:         ${NEXT_PUBLIC_API_BASE_URL}"
if [[ "${START_STREAMLIT}" == "1" || "${START_STREAMLIT}" == "true" || "${START_STREAMLIT}" == "yes" ]]; then
  echo "   Streamlit:        http://${STREAMLIT_HOST}:${STREAMLIT_PORT}"
fi
echo

start_service "backend" "${BACKEND_CMD[@]}"
start_service "nextjs" "${FRONTEND_CMD[@]}"

if [[ "${START_STREAMLIT}" == "1" || "${START_STREAMLIT}" == "true" || "${START_STREAMLIT}" == "yes" ]]; then
  start_service "streamlit" "${STREAMLIT_CMD[@]}"
fi

echo
echo "✅ Services are starting. Press Ctrl+C to stop all services."

monitor_services
