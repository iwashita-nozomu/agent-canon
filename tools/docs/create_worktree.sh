#!/usr/bin/env bash
# Dependency Files:
# - vendor/agent-canon/AGENTS.md
# - vendor/agent-canon/tools/README.md
# - vendor/agent-canon/documents/dependency-headers.md

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

echo "[compat] tools/docs/create_worktree.sh delegates to tools/setup_worktree.sh" >&2
exec bash "${ROOT_DIR}/setup_worktree.sh" "$@"
