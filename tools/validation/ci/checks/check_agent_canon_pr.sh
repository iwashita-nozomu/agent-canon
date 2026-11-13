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
# upstream implementation ../../../runtime/dispatch/agent-canon/src/generated_completeness.rs materializes the post-check G2 receipt
# upstream implementation ../../../runtime/dispatch/agent-canon/src/runtime_alignment.rs native Codex runtime role alignment check
# upstream implementation ../../../runtime/dispatch/agent-canon/src/convention_compliance.rs convention gate wiring eval
# upstream implementation ../../../runtime/dispatch/agent-canon/src/update_lifecycle_contract.rs owns G1-G3 receipt identity.
# upstream implementation ../../../runtime/dispatch/agent-canon/src/main.rs owns the Rust CLI build gate.
# upstream implementation ../../../runtime/dispatch/agent-canon/src/github_workflow_check.rs GitHub workflow and PR template checks
# upstream implementation run_python_quality_checks.sh owns shared Python static quality checks
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
CANON_CI_ROOT="${WORKSPACE_ROOT}/tools/validation/ci"
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

# Runtime artifacts use one validated external root.  The Python boundary is
# shared with producers and archive readers; no source-local fallback exists.
runtime_boundary_root() {
  "${AGENT_CANON_NATIVE_BIN:-${AGENT_CANON_CLI:-${WORKSPACE_ROOT}/tools/bin/agent-canon}}" runtime-paths root --source-root "${AGENT_CANON_SOURCE_ROOT}" --runtime-root "$1"
}

runtime_boundary_path() {
  "${AGENT_CANON_NATIVE_BIN:-${AGENT_CANON_CLI:-${WORKSPACE_ROOT}/tools/bin/agent-canon}}" runtime-paths path --source-root "${AGENT_CANON_SOURCE_ROOT}" --runtime-root "${AGENT_CANON_RUNTIME_ROOT}" --candidate "$1"
}

AGENT_CANON_RUNTIME_ROOT="$(runtime_boundary_root "${AGENT_CANON_RUNTIME_ROOT}")"
export AGENT_CANON_RUNTIME_ROOT
AGENT_CANON_CLI_TARGET_DIR="$(runtime_boundary_path "${AGENT_CANON_CLI_TARGET_DIR:-${AGENT_CANON_RUNTIME_ROOT}/cache/cargo-target}")"
export AGENT_CANON_CLI_TARGET_DIR
CARGO_TARGET_DIR="$(runtime_boundary_path "${CARGO_TARGET_DIR:-${AGENT_CANON_CLI_TARGET_DIR}}")"
export CARGO_TARGET_DIR
CARGO_HOME="$(runtime_boundary_path "${CARGO_HOME:-${AGENT_CANON_RUNTIME_ROOT}/cache/cargo-home}")"
export CARGO_HOME
export TMPDIR="$(runtime_boundary_path "${TMPDIR:-${AGENT_CANON_RUNTIME_ROOT}/tmp}")"
mkdir -p "${AGENT_CANON_CLI_TARGET_DIR}" "${CARGO_HOME}" "${TMPDIR}"

AGENT_CANON_PR_TEMP_ROOT="$(runtime_boundary_path "${AGENT_CANON_PR_TEMP_ROOT:-${AGENT_CANON_RUNTIME_ROOT}/tasks/pr-check-${BASHPID}}")"
mkdir -p "${AGENT_CANON_PR_TEMP_ROOT}"
cleanup_agent_canon_pr_temp_root() {
  local status=$?
  local cleanup_status=0
  trap - EXIT
  rm -rf -- "${AGENT_CANON_PR_TEMP_ROOT}" || cleanup_status=$?
  if [[ "$status" -eq 0 && "$cleanup_status" -ne 0 ]]; then
    status=$cleanup_status
  fi
  exit "$status"
}
trap cleanup_agent_canon_pr_temp_root EXIT
AGENT_CANON_G1_BUNDLE_ACTIVE=0
PR_AGENT_CANON_SOURCE_ROOT="${WORKSPACE_ROOT}"

REMOTE_NAME="${AGENT_CANON_REMOTE_NAME:-agent-canon}"
AGENT_CANON_GITHUB_REPO="${AGENT_CANON_GITHUB_REPO:-iwashita-nozomu/agent-canon}"
REMOTE_URL="<unset>"
if git remote get-url "${REMOTE_NAME}" >/dev/null 2>&1; then
  REMOTE_URL="$(git remote get-url "${REMOTE_NAME}")"
fi
run_direct_agent_checks() {
  run_convention_compliance_gate
  run_agent_canon check-agent-runtime-alignment --root "${WORKSPACE_ROOT}"
}

run_convention_compliance_gate() {
  run_agent_canon check-convention-compliance --root "${WORKSPACE_ROOT}" --format json
}

run_agent_canon() {
  local command=()
  if [ -x "${CANON_TOOLS_ROOT}/bin/agent-canon" ]; then
    command=("${CANON_TOOLS_ROOT}/bin/agent-canon" "$@")
  elif [ -x "${AGENT_CANON_SOURCE_ROOT}/tools/bin/agent-canon" ]; then
    command=("${AGENT_CANON_SOURCE_ROOT}/tools/bin/agent-canon" "$@")
  else
    echo "AGENT_CANON_CLI_BLOCKER=agent_canon_cli_unavailable" >&2
    echo "AGENT_CANON_CLI_REASON=bootstrap-managed AgentCanon CLI is unavailable" >&2
    return 127
  fi
  "${command[@]}"
}

run_pr_agent_checks() {
  run_standalone_static_gate_ci
}

run_pr_project_quality_boundary() {
  echo "AGENT_CANON_PR_PROJECT_QUALITY=delegated"
  echo "AGENT_CANON_PR_PROJECT_QUALITY_OWNER=agentcanon_project_ci"
  echo "AGENT_CANON_PR_PROJECT_QUALITY_WORKFLOW=external_required_job"
  return 0
}

consume_source_correctness_receipt() {
  local bundle="${AGENT_CANON_PR_GATE_BUNDLE:-}"
  if [[ -z "${bundle}" ]]; then
    echo "AGENT_CANON_G1_RECEIPT=not_materialized_nontransaction"
    return
  fi
  run_agent_canon runtime-paths gate-g1 --input "${bundle}"
  AGENT_CANON_G1_BUNDLE_ACTIVE=1
}

emit_generated_completeness_receipt() {
  local bundle="${AGENT_CANON_PR_GATE_BUNDLE:-}"
  local output="${AGENT_CANON_G2_OUTPUT:-}"
  local args=(
    materialize-agent-canon-pr-g2
    --g1-bundle "${bundle}"
    --source-root "${PR_AGENT_CANON_SOURCE_ROOT}"
    --control-parent-root "${AGENT_CANON_CONTROL_PARENT_ROOT}"
    --runtime-root "${AGENT_CANON_RUNTIME_ROOT}"
  )
  if [[ "${AGENT_CANON_G1_BUNDLE_ACTIVE}" -ne 1 ]]; then
    echo "AGENT_CANON_G2_RECEIPT=not_materialized_nontransaction"
    return
  fi
  if [[ -n "${output}" ]]; then
    output="$(runtime_boundary_path "${output}")"
    args+=(--output "${output}")
  fi
  run_agent_canon "${args[@]}"
}

run_standalone_static_gate_ci() {
  echo "AGENT_CANON_STATIC_GATE_UNITS=owned_by_bootstrap_container_workflow"
}

github_repo_security_status() {
  local repo="$1"
  local label="$2"
  local repo_json=""
  local remote_sha=""
  echo "${label}_repo=${repo}"
  if ! command -v gh >/dev/null 2>&1; then
    echo "${label}_gh=unavailable"
    return
  fi
  if repo_json="$(gh repo view "${repo}" --json nameWithOwner,visibility,isPrivate,defaultBranchRef 2>/dev/null)"; then
    echo "${label}_gh=visible"
    echo "${label}_metadata=${repo_json}"
  else
    echo "${label}_gh=not_visible_or_not_created"
    return
  fi
  if remote_sha="$(git ls-remote "https://github.com/${repo}.git" main 2>/dev/null | awk '{print $1}')"; then
    echo "${label}_github_main_sha=${remote_sha:-<missing>}"
  else
    echo "${label}_github_main_sha=<unavailable>"
  fi
  if gh api "repos/${repo}/branches/main/protection" >/dev/null 2>&1; then
    echo "${label}_branch_protection=enabled"
  else
    echo "${label}_branch_protection=missing_or_unavailable"
  fi
  if gh api "repos/${repo}/vulnerability-alerts" >/dev/null 2>&1; then
    echo "${label}_vulnerability_alerts=enabled"
  else
    echo "${label}_vulnerability_alerts=disabled_or_unavailable"
  fi
  if gh api "repos/${repo}/dependabot/alerts" --jq length >/dev/null 2>&1; then
    echo "${label}_dependabot_alerts=readable"
  else
    echo "${label}_dependabot_alerts=disabled_or_scope_missing"
  fi
}

echo "=========================================="
echo "AGENT-CANON PR CHECK"
echo "=========================================="
echo "workspace_root=${WORKSPACE_ROOT}"
echo "agent_canon_pr_temp_root=${AGENT_CANON_PR_TEMP_ROOT}"
echo "agent_canon_remote=${REMOTE_URL}"
consume_source_correctness_receipt
echo ""

echo "1️⃣  GitHub workflow and PR template checks"
run_agent_canon check-github-workflows --root "${WORKSPACE_ROOT}"
echo ""

echo "2️⃣  changed AgentCanon paths"
git status --short -- .github agents documents tools rust tests || true
echo ""

echo "3️⃣  GitHub security evidence"
github_repo_security_status "${AGENT_CANON_GITHUB_REPO}" "agent_canon_github"
echo ""

echo "4️⃣  agent runtime checks"
run_pr_agent_checks
echo ""

echo ""

echo "5️⃣  documentation checks"
run_agent_canon docs check
echo ""

echo "6️⃣  project quality ownership boundary"
run_pr_project_quality_boundary
echo ""

echo "6b️⃣  generated artifact guard"
run_agent_canon generated-artifact-guard --root "${WORKSPACE_ROOT}"
echo ""

emit_generated_completeness_receipt
echo ""

echo "AGENT_CANON_PR_CHECK=pass"
echo "AGENT_CANON_PR_PROPAGATION_WORKFLOW=agents/skills/agent-canon-update.md"
echo "NEXT_ACTION=Open_or_update_AgentCanon_PR_then_read_back_merged_main"
