#!/usr/bin/env bash
# Re-index the sample past proposals into Postgres + pgvector.
# Safe to run multiple times — indexer wipes past_proposals first.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/_common.sh"

load_env
PY="$(venv_python)"

wait_for_postgres
c_blue "[seed_data] re-indexing past proposals..."
"${PY}" -m services.api.rag.indexer
c_green "[seed_data] done."
