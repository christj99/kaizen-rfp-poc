#!/usr/bin/env bash
# Demo "oh no" button: wipe all user data, re-seed past proposals, verify /health.
# Target: under 60 seconds end-to-end.
#
# What it does:
#   1. Stop uvicorn + streamlit (fast kill via pid files)
#   2. TRUNCATE user tables (much faster than DROP/CREATE; schema stays intact)
#   3. Re-index past proposals (OpenAI embeddings call — biggest single cost)
#   4. Restart uvicorn + streamlit
#   5. /health check
#
# What it does NOT do:
#   - Pull new SAM.gov records (quota-protective)
#   - Pull new emails from Gmail (mark_as_read on previous runs means most
#     are already SEEN; a fresh send from the user re-triggers the pipeline)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/_common.sh"

START_TIME=$(date +%s)

load_env
PY="$(venv_python)"

c_blue "[demo_reset] stopping Python services..."
for pid_file in "${REPO_ROOT}/.uvicorn.pid" "${REPO_ROOT}/.streamlit.pid"; do
  if [[ -f "${pid_file}" ]]; then
    pid="$(cat "${pid_file}")"
    if kill -0 "${pid}" 2>/dev/null; then
      kill "${pid}" 2>/dev/null || true
      sleep 0.5
      kill -9 "${pid}" 2>/dev/null || true
    fi
    rm -f "${pid_file}"
  fi
done

wait_for_postgres

c_blue "[demo_reset] truncating user tables..."
"${PY}" - <<'PY'
from services.api.db.client import db_cursor
with db_cursor() as cur:
    # Order matters because of FKs: draft_jobs -> drafts -> screenings -> rfps,
    # proposal_chunks -> past_proposals, audit_log independent.
    cur.execute("""
        TRUNCATE TABLE
            draft_jobs, drafts, screenings, rfps,
            proposal_chunks, past_proposals,
            audit_log
        RESTART IDENTITY CASCADE
    """)
    print("[demo_reset] tables truncated")
PY

c_blue "[demo_reset] re-indexing past proposals..."
"${PY}" -m services.api.rag.indexer

c_blue "[demo_reset] starting FastAPI..."
mkdir -p "${LOG_DIR}"
(
  cd "${REPO_ROOT}"
  nohup "${PY}" -m uvicorn services.api.main:app \
    --host "${API_HOST:-0.0.0.0}" \
    --port "${API_PORT:-8000}" \
    >"${LOG_DIR}/api.log" 2>&1 &
  echo $! > "${REPO_ROOT}/.uvicorn.pid"
)

c_blue "[demo_reset] starting Streamlit..."
(
  cd "${REPO_ROOT}"
  nohup "${PY}" -m streamlit run services/ui/app.py \
    --server.port "${STREAMLIT_PORT:-8501}" \
    --server.headless true \
    >"${LOG_DIR}/ui.log" 2>&1 &
  echo $! > "${REPO_ROOT}/.streamlit.pid"
)

# Give uvicorn a full ~25s to bind; cold-start after a kill cycle on some
# systems takes 10-15s.
for i in $(seq 1 25); do
  if curl -sf "http://localhost:${API_PORT:-8000}/health" >/dev/null; then
    break
  fi
  sleep 1
done

END_TIME=$(date +%s)
ELAPSED=$((END_TIME - START_TIME))

c_green ""
c_green "[demo_reset] done in ${ELAPSED}s."
c_green "  UI:     http://localhost:${STREAMLIT_PORT:-8501}"
c_green "  API:    http://localhost:${API_PORT:-8000}/docs"
curl -sf "http://localhost:${API_PORT:-8000}/health" || c_red "WARN: /health did not come back ok"
echo
