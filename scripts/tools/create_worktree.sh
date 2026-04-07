#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

echo "[compat] scripts/tools/create_worktree.sh delegates to scripts/setup_worktree.sh" >&2
exec bash "${ROOT_DIR}/setup_worktree.sh" "$@"
