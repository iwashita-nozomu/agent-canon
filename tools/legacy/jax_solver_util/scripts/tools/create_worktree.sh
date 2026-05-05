#!/usr/bin/env bash
# @dependency-start
# responsibility Preserves imported jax_solver_util legacy script for provenance.
# upstream design ../README.md legacy import policy
# @dependency-end
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

echo "[compat] scripts/tools/create_worktree.sh delegates to scripts/setup_worktree.sh" >&2
exec bash "${ROOT_DIR}/setup_worktree.sh" "$@"
