#!/usr/bin/env bash
# @dependency-start
# responsibility Checks docker build CI readiness.
# upstream design ../README.md shared automation index
# @dependency-end

set -euo pipefail

WORKSPACE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
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

exec "$PYTHON_BIN" tools/ci/run_container_pack.py "$@"
