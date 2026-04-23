#!/usr/bin/env bash
# Bring up the full Kaizen RFP POC stack: Postgres, n8n, FastAPI, Streamlit.
# Idempotent — safe to run multiple times.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/_common.sh"

c_blue "[demo] checking prerequisites..."
require_cmd docker
require_cmd python

if [[ ! -f "${REPO_ROOT}/.env" ]]; then
  die ".env not found. Copy .env.example to .env and fill in ANTHROPIC_API_KEY first."
fi

load_env

PY="$(venv_python)"

c_blue "[demo] starting Docker services (Postgres + n8n)..."
docker_compose up -d

wait_for_postgres

c_blue "[demo] applying DB schema if needed..."
"${PY}" "${REPO_ROOT}/services/api/db/migrate.py"

# --- FastAPI ---
API_PID_FILE="${REPO_ROOT}/.uvicorn.pid"
if [[ -f "${API_PID_FILE}" ]] && kill -0 "$(cat "${API_PID_FILE}")" 2>/dev/null; then
  c_yellow "[demo] FastAPI already running (pid $(cat "${API_PID_FILE}"))."
else
  c_blue "[demo] starting FastAPI on :${API_PORT:-8000}..."
  (
    cd "${REPO_ROOT}"
    nohup "${PY}" -m uvicorn services.api.main:app \
      --host "${API_HOST:-0.0.0.0}" \
      --port "${API_PORT:-8000}" \
      >"${LOG_DIR}/api.log" 2>&1 &
    echo $! > "${API_PID_FILE}"
  )
fi

# --- Streamlit ---
UI_PID_FILE="${REPO_ROOT}/.streamlit.pid"
if [[ -f "${UI_PID_FILE}" ]] && kill -0 "$(cat "${UI_PID_FILE}")" 2>/dev/null; then
  c_yellow "[demo] Streamlit already running (pid $(cat "${UI_PID_FILE}"))."
else
  c_blue "[demo] starting Streamlit on :${STREAMLIT_PORT:-8501}..."
  (
    cd "${REPO_ROOT}"
    nohup "${PY}" -m streamlit run services/ui/app.py \
      --server.port "${STREAMLIT_PORT:-8501}" \
      --server.headless true \
      >"${LOG_DIR}/ui.log" 2>&1 &
    echo $! > "${UI_PID_FILE}"
  )
fi

sleep 2

c_green ""
c_green "Kaizen RFP POC is up."
c_green "  Streamlit UI   http://localhost:${STREAMLIT_PORT:-8501}"
c_green "  FastAPI docs   http://localhost:${API_PORT:-8000}/docs"
c_green "  n8n            http://localhost:${N8N_PORT:-5678}  (user: ${N8N_BASIC_AUTH_USER:-admin})"
c_green ""
c_green "Logs: logs/api.log  logs/ui.log"
c_green "Stop:  ./scripts/demo_stop.sh"
