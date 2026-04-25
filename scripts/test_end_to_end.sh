#!/usr/bin/env bash
# End-to-end smoke test. Verifies the full ingestion → screening → drafting
# pipeline against the running stack. Designed to run in under 8 minutes
# (drafting via streaming Sonnet is the bottleneck).
#
# What it checks:
#   1. Services healthy (Postgres, FastAPI, n8n)
#   2. Seed loader runs cleanly
#   3. Manual-upload ingest path (POST /rfp/ingest)
#   4. URL-ingest path (POST /rfp/ingest_url)
#   5. Email-adapter health (POST /discovery/run/demo_gmail with no new mail)
#   6. SAM.gov-adapter health (skipped against live API by default; opt-in via SAM_LIVE=1)
#   7. Manual screening path (POST /rfp/{id}/screen)
#   8. Async drafting path (POST /rfp/{id}/draft?mode=async + poll until completed/failed)
#   9. Markdown export (GET /draft/{id}/export)
#  10. Watcher / dashboard query shapes (GET /draft_jobs?status=completed&since=...)
#
# What it doesn't check (out of scope for an automated CI-style run):
#   - Live email send → IMAP pickup (requires real Gmail send)
#   - Live SAM.gov pulls (rate-limited; controlled via SAM_LIVE env var)
#   - n8n workflow execution (covered by manual demo walkthrough)
#   - Streamlit page renders (covered by manual demo walkthrough)

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/_common.sh"

load_env
PY="$(venv_python)"
API="http://localhost:${API_PORT:-8000}"

# Counters
PASS=0
FAIL=0
FAILED_TESTS=()

_pass() { c_green "  PASS  $1"; PASS=$((PASS+1)); }
_fail() { c_red   "  FAIL  $1  ($2)"; FAIL=$((FAIL+1)); FAILED_TESTS+=("$1"); }
_note() { printf "  ----  %s\n" "$1"; }

c_blue "[e2e] === Service health ==="

if curl -sf "${API}/health" | grep -q '"status":"ok"'; then
  _pass "FastAPI /health"
else
  _fail "FastAPI /health" "not reachable"
  c_red "[e2e] aborting — API is required for the rest of the suite."
  exit 1
fi

if docker exec kaizen_postgres pg_isready -U "${POSTGRES_USER:-kaizen}" -d "${POSTGRES_DB:-kaizen_rfp}" >/dev/null 2>&1; then
  _pass "Postgres pg_isready"
else
  _fail "Postgres pg_isready" "container down"
fi

if curl -sf "http://localhost:${N8N_PORT:-5678}/healthz" >/dev/null 2>&1; then
  _pass "n8n /healthz"
else
  _note "n8n /healthz unreachable (workflows are optional; see README)"
fi

c_blue "[e2e] === Seed loader ==="
"${PY}" "${SCRIPT_DIR}/load_seed_fixtures.py" >/tmp/e2e_seed.log 2>&1 \
  && _pass "scripts/load_seed_fixtures.py" \
  || { _fail "scripts/load_seed_fixtures.py" "see /tmp/e2e_seed.log"; cat /tmp/e2e_seed.log; }

c_blue "[e2e] === Ingestion paths ==="

# Manual upload (text path)
INGEST_HASH="e2e-manual-$(date +%s)"
RESP=$(curl -sf -X POST "${API}/rfp/ingest" \
  -H 'Content-Type: application/json' \
  -d "{\"source_type\":\"manual_upload\",\"title\":\"E2E manual ingest test\",\"full_text\":\"Test RFP. NAICS 541511. DHHS data warehouse modernization. Snowflake+dbt+FedRAMP.\",\"agency\":\"E2E HHS\",\"naics_codes\":[\"541511\"],\"dedupe_hash\":\"${INGEST_HASH}\"}" 2>/dev/null)
TEST_RFP_ID=$(echo "${RESP}" | "${PY}" -c "import json,sys; print(json.loads(sys.stdin.read())['rfp']['id'])" 2>/dev/null || true)
if [[ -n "${TEST_RFP_ID}" ]]; then
  _pass "POST /rfp/ingest (manual_upload) -> ${TEST_RFP_ID:0:8}"
else
  _fail "POST /rfp/ingest (manual_upload)" "no rfp id in response: ${RESP:0:200}"
fi

# URL ingest (against example.com — known-stable)
URL_RESP=$(curl -sf -X POST "${API}/rfp/ingest_url" \
  -H 'Content-Type: application/json' \
  -d '{"url":"https://example.com/","title":"E2E url ingest test"}' 2>/dev/null)
URL_RFP_ID=$(echo "${URL_RESP}" | "${PY}" -c "import json,sys; print(json.loads(sys.stdin.read())['rfp']['id'])" 2>/dev/null || true)
if [[ -n "${URL_RFP_ID}" ]]; then
  _pass "POST /rfp/ingest_url -> ${URL_RFP_ID:0:8}"
else
  _fail "POST /rfp/ingest_url" "no rfp id"
fi

c_blue "[e2e] === Adapter health ==="
ADAPTERS=$(curl -sf "${API}/discovery/adapters" 2>/dev/null)
if echo "${ADAPTERS}" | grep -q '"status":"ok"'; then
  _pass "GET /discovery/adapters -> at least one adapter status=ok"
else
  _fail "GET /discovery/adapters" "no ok-status adapters"
fi

# Email adapter run-now (no-op when inbox is empty; should not error)
EMAIL_RESP=$(curl -sf -X POST "${API}/discovery/run/demo_gmail" 2>/dev/null)
if echo "${EMAIL_RESP}" | grep -q '"adapter_name":"demo_gmail"'; then
  _pass "POST /discovery/run/demo_gmail (returned cleanly; new=$(echo "${EMAIL_RESP}" | "${PY}" -c "import json,sys;print(json.loads(sys.stdin.read())['total_new'])"))"
else
  _fail "POST /discovery/run/demo_gmail" "unexpected response"
fi

# SAM.gov adapter only when explicitly opted-in (rate-limited)
if [[ "${SAM_LIVE:-0}" == "1" ]]; then
  SAM_RESP=$(curl -sf -X POST "${API}/discovery/run/sam_gov_primary" 2>/dev/null)
  if echo "${SAM_RESP}" | grep -q 'sam_gov_primary'; then
    _pass "POST /discovery/run/sam_gov_primary (live; rate-limit-aware)"
  else
    _fail "POST /discovery/run/sam_gov_primary" "unexpected response"
  fi
else
  _note "SAM.gov live test skipped (set SAM_LIVE=1 to opt in; uses daily quota)"
fi

c_blue "[e2e] === Screening + drafting (against the manual-ingest test RFP) ==="

if [[ -n "${TEST_RFP_ID:-}" ]]; then
  SCREEN_RESP=$(curl -sf -X POST "${API}/rfp/${TEST_RFP_ID}/screen" 2>/dev/null)
  FIT=$(echo "${SCREEN_RESP}" | "${PY}" -c "import json,sys; print(json.loads(sys.stdin.read())['fit_score'])" 2>/dev/null || true)
  if [[ -n "${FIT}" && "${FIT}" != "None" ]]; then
    _pass "POST /rfp/{id}/screen  fit_score=${FIT}"
  else
    _fail "POST /rfp/{id}/screen" "no fit_score"
  fi

  # Async draft
  DRAFT_RESP=$(curl -sf -X POST "${API}/rfp/${TEST_RFP_ID}/draft?mode=async" 2>/dev/null)
  JOB_ID=$(echo "${DRAFT_RESP}" | "${PY}" -c "import json,sys; print(json.loads(sys.stdin.read())['job_id'])" 2>/dev/null || true)
  if [[ -n "${JOB_ID}" ]]; then
    _pass "POST /rfp/{id}/draft?mode=async  job_id=${JOB_ID:0:8}"
    # Poll for completion (cap at 7 min)
    c_blue "  [e2e] polling draft job ${JOB_ID:0:8} (cap 7 min) ..."
    for i in $(seq 1 42); do
      STATUS=$(curl -sf "${API}/draft/job/${JOB_ID}" 2>/dev/null | "${PY}" -c "import json,sys; print(json.loads(sys.stdin.read())['job']['status'])" 2>/dev/null || echo "?")
      if [[ "${STATUS}" == "completed" || "${STATUS}" == "failed" ]]; then
        break
      fi
      sleep 10
    done
    if [[ "${STATUS}" == "completed" ]]; then
      _pass "draft job completed"
      DRAFT_ID=$(curl -sf "${API}/draft/job/${JOB_ID}" 2>/dev/null | "${PY}" -c "import json,sys; print(json.loads(sys.stdin.read())['job']['draft_id'])" 2>/dev/null)
      EXPORT_BYTES=$(curl -sf "${API}/draft/${DRAFT_ID}/export" 2>/dev/null | wc -c)
      if [[ "${EXPORT_BYTES}" -gt 5000 ]]; then
        _pass "GET /draft/{id}/export  (${EXPORT_BYTES} bytes of Markdown)"
      else
        _fail "GET /draft/{id}/export" "suspiciously small (${EXPORT_BYTES} bytes)"
      fi
    elif [[ "${STATUS}" == "failed" ]]; then
      _fail "draft job" "ended in failed status"
    else
      _fail "draft job" "still running after 7 min (last status=${STATUS})"
    fi
  else
    _fail "POST /rfp/{id}/draft?mode=async" "no job_id"
  fi
else
  _note "skipping screening + drafting (manual ingest didn't produce an RFP id)"
fi

c_blue "[e2e] === Watcher query shape ==="
WATCHER_RESP=$(curl -sf "${API}/draft_jobs?status=completed&limit=5" 2>/dev/null)
if echo "${WATCHER_RESP}" | "${PY}" -c "import json,sys; data=json.loads(sys.stdin.read()); assert isinstance(data,list); print(len(data))" >/dev/null 2>&1; then
  _pass "GET /draft_jobs?status=completed&limit=5  (returns array)"
else
  _fail "GET /draft_jobs?status=completed" "non-array response"
fi

# Final summary
echo
echo "==========================="
if [[ ${FAIL} -eq 0 ]]; then
  c_green "  PASS  e2e: ${PASS}/${PASS} checks"
  exit 0
else
  c_red "  FAIL  e2e: ${PASS} passed, ${FAIL} failed"
  c_red "  failed checks: ${FAILED_TESTS[*]}"
  exit 1
fi
