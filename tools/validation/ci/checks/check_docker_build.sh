#!/usr/bin/env bash
# @dependency-start
# contract tool
# responsibility Checks docker build CI readiness.
# upstream design ../../../README.md shared automation index
# @dependency-end

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
source "${SCRIPT_DIR}/../../../repository/support/repo_paths.sh"
WORKSPACE_ROOT="$(agent_canon_repo_root "${BASH_SOURCE[0]}")"
CANON_TOOLS_ROOT="$(agent_canon_source_tools_root "$WORKSPACE_ROOT")"
cd "$WORKSPACE_ROOT"

exec "${CANON_TOOLS_ROOT}/bin/agent-canon" run-container-pack "$@"
