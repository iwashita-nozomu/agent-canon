#!/usr/bin/env bash
# @dependency-start
# contract tool
# responsibility Checks docker build CI readiness.
# upstream design ../README.md shared automation index
# @dependency-end

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
source "${SCRIPT_DIR}/../lib/repo_paths.sh"
WORKSPACE_ROOT="$(agent_canon_repo_root "${BASH_SOURCE[0]}")"
CANON_TOOLS_ROOT="$(agent_canon_source_tools_root "$WORKSPACE_ROOT")"
CANON_CI_ROOT="${CANON_TOOLS_ROOT}/ci"
cd "$WORKSPACE_ROOT"

PYTHON_BIN="${PYTHON_BIN:-}"
if [ -z "$PYTHON_BIN" ]; then
  if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
  elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="python"
  else
    echo "python3 or python is required to run docker build checks" >&2
    exit 127
  fi
fi

exec "$PYTHON_BIN" "${CANON_CI_ROOT}/run_container_pack.py" "$@"
