#!/usr/bin/env bash
# Shared helpers for scripts/. Source this from other scripts.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
LOG_DIR="${REPO_ROOT}/logs"
mkdir -p "${LOG_DIR}"

c_red()   { printf "\033[31m%s\033[0m\n" "$*"; }
c_green() { printf "\033[32m%s\033[0m\n" "$*"; }
c_yellow(){ printf "\033[33m%s\033[0m\n" "$*"; }
c_blue()  { printf "\033[34m%s\033[0m\n" "$*"; }

die() { c_red "ERROR: $*" >&2; exit 1; }

load_env() {
  if [[ -f "${REPO_ROOT}/.env" ]]; then
    # shellcheck disable=SC1091
    set -a; source "${REPO_ROOT}/.env"; set +a
  fi
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "required command not found: $1"
}

docker_compose() {
  # Prefer the v2 plugin; fall back to legacy docker-compose.
  if docker compose version >/dev/null 2>&1; then
    (cd "${REPO_ROOT}" && docker compose "$@")
  else
    (cd "${REPO_ROOT}" && docker-compose "$@")
  fi
}

venv_python() {
  # Git Bash on Windows puts the interpreter in Scripts/; Unix uses bin/.
  if [[ -x "${REPO_ROOT}/.venv/Scripts/python.exe" ]]; then
    echo "${REPO_ROOT}/.venv/Scripts/python.exe"
  elif [[ -x "${REPO_ROOT}/.venv/bin/python" ]]; then
    echo "${REPO_ROOT}/.venv/bin/python"
  else
    die "Python venv not found at .venv/. Create it with: python -m venv .venv && pip install -r requirements.txt"
  fi
}

wait_for_postgres() {
  c_blue "[demo] waiting for Postgres to accept connections..."
  local tries=30
  while (( tries-- > 0 )); do
    if docker exec kaizen_postgres pg_isready -U "${POSTGRES_USER:-kaizen}" -d "${POSTGRES_DB:-kaizen_rfp}" >/dev/null 2>&1; then
      c_green "[demo] Postgres is ready."
      return 0
    fi
    sleep 1
  done
  die "Postgres did not become ready in time."
}
