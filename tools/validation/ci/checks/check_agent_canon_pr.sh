#!/usr/bin/env bash
# @dependency-start
# contract tool
# responsibility Checks AgentCanon PR readiness for the retained PR-owned checks.
# upstream design ../../../README.md shared automation index
# upstream design ../../../../agents/skills/agent-canon-update.md shared canon PR workflow
# upstream design ../../../../.github/PULL_REQUEST_TEMPLATE.md standalone AgentCanon PR checklist
# upstream implementation ../../../runtime/dispatch/agent-canon/src/runtime_paths.rs validates explicit control/runtime paths
# upstream implementation ../../../runtime/dispatch/agent-canon/src/runtime_boundary.rs owns PR scratch, archive, and receipt output boundaries
# upstream implementation ../../../runtime/dispatch/agent-canon/src/report_artifact_checks.rs rejects regenerated report leftovers before PR check pass
# upstream implementation ../../../runtime/dispatch/agent-canon/src/github_workflow_check.rs native GitHub workflow analyzers
# @dependency-end

set -euo pipefail

if [[ "$#" -ne 0 ]]; then
  echo "usage: $0" >&2
  exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
source "${SCRIPT_DIR}/../../../repository/support/repo_paths.sh"
WORKSPACE_ROOT="$(agent_canon_repo_root "${BASH_SOURCE[0]}")"
CANON_TOOLS_ROOT="$(agent_canon_source_tools_root "${WORKSPACE_ROOT}")"
AGENT_CANON_SOURCE_ROOT="${WORKSPACE_ROOT}"
cd "${WORKSPACE_ROOT}"
# The source checkout is read-only input.  A caller must provide both the
# separately authenticated control checkout and an external runtime root;
# silently promoting the source checkout (or TMPDIR) to either authority is a
# source-side-effect bug.
if [[ -z "${AGENT_CANON_CONTROL_PARENT_ROOT:-}" ]]; then
  echo "AGENT_CANON_PR_BOUNDARY=fail reason=control_parent_root_required" >&2
  exit 2
fi
if [[ -z "${AGENT_CANON_RUNTIME_ROOT:-}" ]]; then
  echo "AGENT_CANON_PR_BOUNDARY=fail reason=runtime_root_required" >&2
  exit 2
fi
if ! "${AGENT_CANON_NATIVE_BIN:-${AGENT_CANON_CLI:-${WORKSPACE_ROOT}/tools/bin/agent-canon}}" runtime-paths check-control --source-root "${AGENT_CANON_SOURCE_ROOT}" --control-parent-root "${AGENT_CANON_CONTROL_PARENT_ROOT}"; then
  echo "AGENT_CANON_PR_BOUNDARY=fail reason=control_parent_root_is_source" >&2
  exit 2
fi
export AGENT_CANON_PARENT_ROOT="${AGENT_CANON_CONTROL_PARENT_ROOT}"
export AGENT_CANON_ACTIVE_REPOSITORY_ROOT="${AGENT_CANON_CONTROL_PARENT_ROOT}"
# The PR gate's explicit runtime capability supersedes unrelated caller
# tmp/cache settings.  Let the boundary derive every child path from that root.
unset TMPDIR TEMP TMP XDG_CACHE_HOME PYTHONPYCACHEPREFIX
unset AGENT_CANON_TOOLS_HOME CARGO_HOME CARGO_TARGET_DIR
unset AGENT_CANON_CLI_TARGET_DIR RUSTUP_HOME ELAN_HOME
unset AGENT_CANON_CHILD_HANDOFF AGENT_CANON_HANDOFF_AUDIENCE AGENT_CANON_CHILD_PURPOSE

runtime_boundary_root() {
  "${AGENT_CANON_NATIVE_BIN:-${AGENT_CANON_CLI:-${WORKSPACE_ROOT}/tools/bin/agent-canon}}" runtime-paths root --source-root "${AGENT_CANON_SOURCE_ROOT}" --runtime-root "$1"
}

runtime_boundary_path() {
  "${AGENT_CANON_NATIVE_BIN:-${AGENT_CANON_CLI:-${WORKSPACE_ROOT}/tools/bin/agent-canon}}" runtime-paths path --source-root "${AGENT_CANON_SOURCE_ROOT}" --runtime-root "${AGENT_CANON_RUNTIME_ROOT}" --candidate "$1"
}

AGENT_CANON_RUNTIME_ROOT="$(runtime_boundary_root "${AGENT_CANON_RUNTIME_ROOT}")"
export AGENT_CANON_RUNTIME_ROOT
export TMPDIR="$(runtime_boundary_path "${AGENT_CANON_RUNTIME_ROOT}/tmp")"
mkdir -p "${TMPDIR}"

cli="${AGENT_CANON_NATIVE_BIN:-${AGENT_CANON_CLI:-${CANON_TOOLS_ROOT}/bin/agent-canon}}"
"${cli}" check-github-workflows --root "${WORKSPACE_ROOT}"
"${cli}" docs check
"${cli}" generated-artifact-guard --root "${WORKSPACE_ROOT}"

echo "AGENT_CANON_PR_CHECK=pass"
