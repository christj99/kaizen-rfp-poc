#!/usr/bin/env bash
# Cleanly stop the Kaizen RFP POC stack.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/_common.sh"

stop_pid_file() {
  local pid_file="$1"
  local name="$2"
  if [[ -f "${pid_file}" ]]; then
    local pid
    pid="$(cat "${pid_file}")"
    if kill -0 "${pid}" 2>/dev/null; then
      c_blue "[demo] stopping ${name} (pid ${pid})..."
      kill "${pid}" 2>/dev/null || true
      sleep 1
      kill -9 "${pid}" 2>/dev/null || true
    fi
    rm -f "${pid_file}"
  else
    c_yellow "[demo] no ${name} pid file at ${pid_file}"
  fi
}

stop_pid_file "${REPO_ROOT}/.uvicorn.pid"  "FastAPI"
stop_pid_file "${REPO_ROOT}/.streamlit.pid" "Streamlit"

c_blue "[demo] stopping Docker services..."
docker_compose down

c_green "[demo] stopped."
