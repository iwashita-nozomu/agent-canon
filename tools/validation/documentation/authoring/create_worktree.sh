#!/usr/bin/env bash
# @dependency-start
# contract tool
# responsibility Rejects legacy create worktree documentation tooling.
# upstream design ../README.md shared automation index
# @dependency-end

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

echo "[compat] tools/docs/create_worktree.sh is deprecated and delegates to the rejecting legacy wrapper" >&2
exec bash "${ROOT_DIR}/setup_worktree.sh" "$@"
