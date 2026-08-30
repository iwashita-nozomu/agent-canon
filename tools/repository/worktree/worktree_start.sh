#!/usr/bin/env bash
# @dependency-start
# contract tool
# responsibility Provides legacy worktree cleanup diagnostic repository automation.
# upstream design ../../README.md shared automation index
# upstream implementation ../workspace/worktree_start.py owns legacy cleanup diagnostics
# @dependency-end

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PYTHON_BIN="${PYTHON_BIN:-}"
if [ -z "$PYTHON_BIN" ]; then
  if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
  elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="python"
  else
    echo "python3 or python is required" >&2
    exit 127
  fi
fi

exec "$PYTHON_BIN" "${SCRIPT_DIR}/../workspace/worktree_start.py" "$@"
