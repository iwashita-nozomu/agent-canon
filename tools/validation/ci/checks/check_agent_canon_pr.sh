#!/usr/bin/env bash
# @dependency-start
# contract tool
# responsibility Checks AgentCanon PR readiness for the retained PR-owned checks.
# upstream design ../../../README.md shared automation index
# upstream design ../../../../agents/skills/agent-canon-update.md shared canon PR workflow
# upstream design ../../../../.github/PULL_REQUEST_TEMPLATE.md standalone AgentCanon PR checklist
# upstream implementation ../../../repository/workspace/parent_root_side_effects.py owns explicit control authentication and child execution
# upstream implementation ../../../runtime/artifacts/runtime_artifacts.py owns PR scratch, archive, and receipt output boundaries
# upstream implementation ../../../../eval/producers/evaluate_skill_workflow_prompts.py skill/workflow prompt parity eval
# upstream implementation ../../../../eval/producers/run_accumulated_agent_evals.py writes required eval family reports before accumulation validation
# upstream implementation ../../../runtime/artifacts/generated_artifact_guard.py rejects regenerated report leftovers before PR check pass
# upstream implementation ../../semantic/runtime/check_agent_runtime_alignment.py Codex runtime role alignment eval
# upstream implementation ../../semantic/convention/check_convention_compliance.py convention gate wiring eval
# upstream implementation ../../../agent/skills/skill_tool_commands.py runtime skill command packet gate
# upstream implementation ../../../runtime/lifecycle/update_lifecycle_contract.py owns G1-G3 receipt identity.
# upstream implementation ../../../runtime/dispatch/agent-canon/src/main.rs owns the Rust CLI build gate.
# upstream implementation ./check_github_workflows.py GitHub workflow and PR template checks
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
AGENT_CANON_BOUNDARY_SCRIPT="${WORKSPACE_ROOT}/tools/repository/workspace/parent_root_side_effects.py"
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
if ! python3 - "${AGENT_CANON_SOURCE_ROOT}" "${AGENT_CANON_CONTROL_PARENT_ROOT}" <<'PY'
from pathlib import Path
import sys

source = Path(sys.argv[1]).resolve(strict=True)
control = Path(sys.argv[2]).resolve(strict=False)
if source == control:
    raise SystemExit("control parent root must differ from source root")
PY
then
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
if [[ "${AGENT_CANON_CHILD_PURPOSE:-}" == "agent-canon-pr-script" ]]; then
  python3 "${AGENT_CANON_BOUNDARY_SCRIPT}" verify-child \
    --root "${AGENT_CANON_CONTROL_PARENT_ROOT}" \
    --source-root "${AGENT_CANON_SOURCE_ROOT}" \
    --purpose agent-canon-pr-script \
    --consume >/dev/null
else
  exec python3 "${AGENT_CANON_BOUNDARY_SCRIPT}" exec-parent-bound \
    --root "${AGENT_CANON_CONTROL_PARENT_ROOT}" \
    --source-root "${AGENT_CANON_SOURCE_ROOT}" \
    --purpose agent-canon-pr-script \
    --issue-handoff \
    -- bash "${BASH_SOURCE[0]}"
fi
unset AGENT_CANON_CHILD_HANDOFF AGENT_CANON_HANDOFF_AUDIENCE AGENT_CANON_CHILD_PURPOSE

# Runtime artifacts use one validated external root.  The Python boundary is
# shared with producers and archive readers; no source-local fallback exists.
runtime_boundary_root() {
  local candidate="$1"
  PYTHONPATH="${WORKSPACE_ROOT}${PYTHONPATH:+:${PYTHONPATH}}" \
    python3 - "${AGENT_CANON_SOURCE_ROOT}" "${candidate}" <<'PY'
from pathlib import Path
import sys

from tools.runtime.artifacts.runtime_artifacts import runtime_artifact_boundary

print(runtime_artifact_boundary(Path(sys.argv[1]), Path(sys.argv[2]), create=True).root)
PY
}

runtime_boundary_path() {
  local candidate="$1"
  PYTHONPATH="${WORKSPACE_ROOT}${PYTHONPATH:+:${PYTHONPATH}}" \
    python3 - "${AGENT_CANON_SOURCE_ROOT}" "${AGENT_CANON_RUNTIME_ROOT}" "${candidate}" <<'PY'
from pathlib import Path
import sys

from tools.runtime.artifacts.runtime_artifacts import runtime_artifact_boundary

boundary = runtime_artifact_boundary(Path(sys.argv[1]), Path(sys.argv[2]), create=True)
print(boundary.resolve(Path(sys.argv[3])))
PY
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
PR_HOOK_ARCHIVE_DIR="${AGENT_CANON_HOOK_ARCHIVE_DIR:-${AGENT_CANON_RUNTIME_ROOT}/archive/agent-canon-log}"
PR_HOOK_ARCHIVE_DIR="$(runtime_boundary_path "${PR_HOOK_ARCHIVE_DIR}")"
mkdir -p "${PR_HOOK_ARCHIVE_DIR}"

REMOTE_NAME="${AGENT_CANON_REMOTE_NAME:-agent-canon}"
AGENT_CANON_GITHUB_REPO="${AGENT_CANON_GITHUB_REPO:-iwashita-nozomu/agent-canon}"
REMOTE_URL="<unset>"
if git remote get-url "${REMOTE_NAME}" >/dev/null 2>&1; then
  REMOTE_URL="$(git remote get-url "${REMOTE_NAME}")"
fi
run_direct_agent_checks() {
  run_convention_compliance_gate
  python3 "${WORKSPACE_ROOT}/tools/validation/semantic/runtime/check_agent_runtime_alignment.py"
  python3 "${WORKSPACE_ROOT}/tools/agent/skills/skill_tool_commands.py" check
}

run_convention_compliance_gate() {
  python3 "${WORKSPACE_ROOT}/tools/validation/semantic/convention/check_convention_compliance.py" --root "${WORKSPACE_ROOT}" --format json
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
  PYTHONPATH="${PR_AGENT_CANON_SOURCE_ROOT}${PYTHONPATH:+:${PYTHONPATH}}" \
    python3 - "${bundle}" <<'PY'
import json
import sys
from pathlib import Path
from tools.runtime.lifecycle.update_lifecycle_contract import validate_gate_chain

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
values = payload.get("gate_verdicts") if isinstance(payload, dict) else None
if not isinstance(values, list):
    raise SystemExit("agent_canon_pr_gate_bundle:gate_verdicts_missing")
validate_gate_chain(values, expected_gate_ids=("G1",), require_pass=True)
print("AGENT_CANON_G1_RECEIPT=consumed")
print("AGENT_CANON_PR_GATE_ORDER=G1")
PY
  AGENT_CANON_G1_BUNDLE_ACTIVE=1
}

emit_generated_completeness_receipt() {
  local bundle="${AGENT_CANON_PR_GATE_BUNDLE:-}"
  local output="${AGENT_CANON_G2_OUTPUT:-}"
  local command=(
    python3 "${PR_AGENT_CANON_SOURCE_ROOT}/tools/validation/ci/checks/check_agent_canon_pr.py"
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
    command+=(--output "${output}")
  fi
  "${command[@]}"
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
python3 "${CANON_CI_ROOT}/checks/check_github_workflows.py"
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
python3 "${WORKSPACE_ROOT}/tools/runtime/artifacts/generated_artifact_guard.py" --root "${WORKSPACE_ROOT}"
echo ""

emit_generated_completeness_receipt
echo ""

echo "AGENT_CANON_PR_CHECK=pass"
echo "AGENT_CANON_PR_PROPAGATION_WORKFLOW=agents/skills/agent-canon-update.md"
echo "NEXT_ACTION=Open_or_update_AgentCanon_PR_then_read_back_merged_main"
