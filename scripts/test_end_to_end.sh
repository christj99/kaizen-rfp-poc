#!/usr/bin/env bash
# End-to-end smoke test. Filled out in Phase 6.
# For Phase 0, it just verifies /health is reachable.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/_common.sh"

load_env

c_blue "[e2e] hitting GET /health..."
if curl -sf "http://localhost:${API_PORT:-8000}/health" >/dev/null; then
  c_green "[e2e] PASS (health check)"
  exit 0
fi
c_red "[e2e] FAIL — API not reachable on :${API_PORT:-8000}"
exit 1
