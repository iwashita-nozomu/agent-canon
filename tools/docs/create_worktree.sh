#!/usr/bin/env bash
# @dependency-start
# upstream design ../README.md shared automation index
# @dependency-end

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

echo "[compat] tools/docs/create_worktree.sh delegates to tools/setup_worktree.sh" >&2
exec bash "${ROOT_DIR}/setup_worktree.sh" "$@"
