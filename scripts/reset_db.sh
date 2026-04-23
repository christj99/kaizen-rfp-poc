#!/usr/bin/env bash
# Drop all tables and reapply schema.sql. Postgres container must already be up.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/_common.sh"

load_env
PY="$(venv_python)"

wait_for_postgres
c_blue "[reset_db] dropping and recreating schema..."
"${PY}" "${REPO_ROOT}/services/api/db/migrate.py" --reset
c_green "[reset_db] done."
