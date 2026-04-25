#!/usr/bin/env bash
# Seed the demo DB to a known state from committed fixtures.
#
# Sequence:
#   1. Wait for Postgres
#   2. If past_proposals empty: run the RAG indexer (slowest step ~10s)
#   3. Load fixtures: TRUNCATE user tables + INSERT from sample_data/seed/*.json
#
# Past proposals + chunks are preserved across reseeds — they only get
# re-indexed when the table is empty.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/_common.sh"

load_env
PY="$(venv_python)"

wait_for_postgres

c_blue "[seed_data] checking past-proposal corpus..."
PP_COUNT=$("${PY}" -c "from services.api.db.client import db_cursor
with db_cursor() as cur:
    cur.execute('SELECT COUNT(*) FROM past_proposals')
    print(cur.fetchone()[0])
" 2>/dev/null || echo 0)

if [[ "${PP_COUNT}" -eq 0 ]]; then
  c_blue "[seed_data] past_proposals empty — running indexer..."
  "${PY}" -m services.api.rag.indexer
else
  c_blue "[seed_data] past_proposals already populated (${PP_COUNT} proposals); skipping reindex."
fi

c_blue "[seed_data] loading fixtures..."
"${PY}" "${SCRIPT_DIR}/load_seed_fixtures.py"

c_green "[seed_data] done."
