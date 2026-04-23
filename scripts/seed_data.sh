#!/usr/bin/env bash
# Loads sample RFPs and past proposals into the database.
# Populated at Phase 6 after Checkpoint 1 delivers the real sample content.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/_common.sh"

c_yellow "[seed_data] not yet implemented — runs after Checkpoint 1 content is delivered."
exit 0
