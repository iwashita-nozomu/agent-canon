#!/usr/bin/env bash
# @dependency-start
# contract tool
# responsibility Checks agent canon pr CI readiness.
# upstream design ../../tools/README.md shared automation index
# upstream design ../../agents/workflows/agent-canon-pr-workflow.md shared canon PR workflow
# upstream design ../../.github/PULL_REQUEST_TEMPLATE.md standalone AgentCanon PR checklist
# upstream design ../../.github/PULL_REQUEST_TEMPLATE/agent_canon.md template AgentCanon PR checklist
# upstream design ../../templates/documents/github/pull-request/agent_canon.md canonical template-side AgentCanon PR checklist
# upstream implementation ../agent_tools/run_repo_dependency_review.sh strict dependency review
# upstream implementation ../agent_tools/evaluate_skill_workflow_prompts.py skill/workflow prompt parity eval
# upstream implementation ../agent_tools/run_accumulated_agent_evals.py writes required eval family reports before accumulation validation
# upstream implementation ../agent_tools/generated_artifact_guard.py rejects regenerated report leftovers before PR check pass
# upstream implementation ../agent_tools/check_agent_runtime_alignment.py Codex runtime role alignment eval
# upstream implementation ../agent_tools/check_convention_compliance.py convention gate wiring eval
# upstream implementation ../agent_tools/skill_tool_commands.py runtime skill command packet gate
# upstream implementation ../agent_tools/update_lifecycle_contract.py owns G1-G3 receipt identity.
# upstream implementation ./check_github_workflows.py GitHub workflow and PR template checks
# upstream implementation ./run_all_checks.sh quick CI implementation
# @dependency-end

set -euo pipefail

if [[ "$#" -ne 0 ]]; then
  echo "usage: $0" >&2
  exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
SUPERPROJECT_ROOT="$(git -C "${SCRIPT_DIR}" rev-parse --show-superproject-working-tree 2>/dev/null || true)"
if [ -n "${SUPERPROJECT_ROOT}" ]; then
  WORKSPACE_ROOT="${SUPERPROJECT_ROOT}"
else
  WORKSPACE_ROOT="$(git -C "${SCRIPT_DIR}" rev-parse --show-toplevel)"
fi
cd "${WORKSPACE_ROOT}"

AGENT_CANON_PR_TEMP_ROOT_CREATED=0
if [[ -z "${AGENT_CANON_PR_TEMP_ROOT:-}" ]]; then
  AGENT_CANON_PR_TEMP_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/agent-canon-pr-check.XXXXXX")"
  AGENT_CANON_PR_TEMP_ROOT_CREATED=1
fi
PR_GATE_RECEIPT="${AGENT_CANON_PR_TEMP_ROOT}/pr-gate-prepared.receipt"
cleanup_agent_canon_pr_temp_root() {
  if [[ -n "${PR_GATE_RECEIPT:-}" ]]; then
    rm -f -- "${PR_GATE_RECEIPT}" 2>/dev/null || true
  fi
  if [[ "${AGENT_CANON_PR_TEMP_ROOT_CREATED}" -eq 1 ]]; then
    rm -rf "${AGENT_CANON_PR_TEMP_ROOT}"
  fi
}
trap cleanup_agent_canon_pr_temp_root EXIT
PR_DEPENDENCY_REVIEW_DIR="${AGENT_CANON_PR_TEMP_ROOT}/dependency-review/agent-canon-pr"
PR_AGENT_EVAL_LOG_DIR="${AGENT_CANON_PR_TEMP_ROOT}/agent-eval-runs/agent-canon-pr-gate"
PR_RUN_ALL_CHECKS_LOG_DIR="${AGENT_CANON_PR_TEMP_ROOT}/agent-eval-runs/run-all-checks"
PR_QUICK_CI_ARGS=(--quick --skip-docs --skip-github-workflows)
AGENT_CANON_G1_BUNDLE_ACTIVE=0
if [[ -d vendor/agent-canon && -f .gitmodules ]]; then
  PR_AGENT_CANON_SOURCE_ROOT="${WORKSPACE_ROOT}/vendor/agent-canon"
else
  PR_AGENT_CANON_SOURCE_ROOT="${WORKSPACE_ROOT}"
fi
PR_HOOK_ARCHIVE_DIR="${AGENT_CANON_HOOK_ARCHIVE_DIR:-${PR_AGENT_CANON_SOURCE_ROOT}/.agent-canon/log-archive}"
mkdir -p "${PR_HOOK_ARCHIVE_DIR}"

REMOTE_NAME="${AGENT_CANON_REMOTE_NAME:-agent-canon}"
AGENT_CANON_GITHUB_REPO="${AGENT_CANON_GITHUB_REPO:-iwashita-nozomu/agent-canon}"
TEMPLATE_GITHUB_REPO="${TEMPLATE_GITHUB_REPO:-iwashita-nozomu/project_template}"
REMOTE_URL="<unset>"
if git remote get-url "${REMOTE_NAME}" >/dev/null 2>&1; then
  REMOTE_URL="$(git remote get-url "${REMOTE_NAME}")"
fi
if [[ -d vendor/agent-canon && -f .gitmodules ]]; then
  AGENT_CANON_REPOSITORY_MODE="template_or_derived"
else
  AGENT_CANON_REPOSITORY_MODE="standalone_source"
fi
run_direct_agent_checks() {
  if [[ "${AGENT_CANON_REPOSITORY_MODE}" == "template_or_derived" ]]; then
    bash tools/sync_agent_canon.sh check
  else
    echo "SHARED_SURFACE_DRIFT=not_applicable_standalone_source"
  fi
  python3 tools/agent_tools/check_agent_runtime_alignment.py
  AGENT_CANON_HOOK_ARCHIVE_DIR="${PR_HOOK_ARCHIVE_DIR}" \
    python3 tools/agent_tools/evaluate_codex_agent_roles.py --accumulate
  AGENT_CANON_HOOK_ARCHIVE_DIR="${PR_HOOK_ARCHIVE_DIR}" \
    python3 tools/agent_tools/evaluate_skill_workflow_prompts.py --manifest evidence/agent-evals/skill_workflow_prompt_eval.toml --accumulate
}

run_shared_surface_status() {
  if [[ "${AGENT_CANON_REPOSITORY_MODE}" == "template_or_derived" ]]; then
    bash tools/sync_agent_canon.sh status
  else
    echo "SHARED_SURFACE_STATUS=not_applicable_standalone_source"
  fi
}

run_shared_surface_check() {
  if [[ "${AGENT_CANON_REPOSITORY_MODE}" == "template_or_derived" ]]; then
    bash tools/sync_agent_canon.sh check
  else
    echo "SHARED_SURFACE_DRIFT=not_applicable_standalone_source"
  fi
}

agentcanon_pr_branch_dirty() {
  local submodule_dirty=""
  if [[ "${AGENT_CANON_REPOSITORY_MODE}" != "template_or_derived" ]]; then
    return 1
  fi
  submodule_dirty="$(git -C vendor/agent-canon status --short --untracked-files=all 2>/dev/null || true)"
  [[ -n "${submodule_dirty}" ]]
}

agentcanon_pr_branch_pending() {
  local submodule_head=""
  local parent_pin=""
  local remote_main=""
  if [[ "${AGENT_CANON_REPOSITORY_MODE}" != "template_or_derived" ]]; then
    return 1
  fi
  if agentcanon_pr_branch_dirty; then
    return 1
  fi
  submodule_head="$(git -C vendor/agent-canon rev-parse HEAD 2>/dev/null || true)"
  parent_pin="$(git rev-parse HEAD:vendor/agent-canon 2>/dev/null || true)"
  if [[ -z "${submodule_head}" || -z "${parent_pin}" ]]; then
    return 1
  fi
  if [[ "${submodule_head}" != "${parent_pin}" ]]; then
    return 1
  fi

  remote_main="$(git ls-remote --exit-code "${REMOTE_URL}" refs/heads/main 2>/dev/null | awk '{print $1}')"
  if [[ -z "${remote_main}" ]]; then
    return 1
  fi
  [[ "${parent_pin}" != "${remote_main}" ]]
}

agentcanon_pr_submodule_remote_reachable() {
  local remote_url="$1"
  local pin_ref="$2"
  if [[ -z "${remote_url}" || -z "${pin_ref}" ]]; then
    return 1
  fi
  if ! git -C vendor/agent-canon cat-file -e "${pin_ref}^{commit}" >/dev/null 2>&1; then
    git -C vendor/agent-canon fetch --no-write-fetch-head "${remote_url}" "${pin_ref}" >/dev/null 2>&1 || return 1
  fi
  git -C vendor/agent-canon cat-file -e "${pin_ref}^{commit}" >/dev/null 2>&1
}

agentcanon_pr_branch_integrity() {
  local submodule_head=""
  local parent_pin=""
  local remote_url="${REMOTE_URL}"
  if [[ "${AGENT_CANON_REPOSITORY_MODE}" != "template_or_derived" ]]; then
    return 0
  fi
  if agentcanon_pr_branch_dirty; then
    echo "AGENT_CANON_PR_LATEST_GATE=blocked_dirty_agentcanon_branch"
    echo "AGENT_CANON_PR_LATEST_NEXT=commit_agentcanon_artifacts_or_explicitly_stash_non_artifact_changes_then_rerun_agent-canon-pr-check"
    return 2
  fi
  submodule_head="$(git -C vendor/agent-canon rev-parse HEAD 2>/dev/null || true)"
  parent_pin="$(git rev-parse HEAD:vendor/agent-canon 2>/dev/null || true)"
  if [[ -z "${submodule_head}" || -z "${parent_pin}" ]]; then
    echo "AGENT_CANON_PR_LATEST_GATE=blocked_agentcanon_submodule_state"
    echo "AGENT_CANON_PR_LATEST_NEXT=repair_submodule_state_and_rerun_agent-canon-pr-check"
    return 3
  fi
  if [[ "${submodule_head}" != "${parent_pin}" ]]; then
    echo "AGENT_CANON_PR_LATEST_GATE=blocked_submodule_gitlink_mismatch"
    echo "AGENT_CANON_PR_LATEST_REASON=submodule-gitlink-worktree-mismatch"
    echo "AGENT_CANON_PR_LATEST_NEXT=run_make_agent-canon-ensure-latest_then_commit_updated_submodule_pin_with_request_evidence"
    return 4
  fi
  if ! agentcanon_pr_submodule_remote_reachable "${remote_url}" "${parent_pin}"; then
    echo "AGENT_CANON_PR_LATEST_GATE=blocked_submodule_pin_unreachable"
    echo "AGENT_CANON_PR_LATEST_REASON=submodule-pinned-commit-unreachable-from-configured-remote"
    echo "AGENT_CANON_PR_LATEST_NEXT=run_agent_canon_update_or_update_agent-canon-remote_reference"
    return 5
  fi
  return 0
}

run_pr_agent_checks() {
  if [[ "${AGENT_CANON_REPOSITORY_MODE}" == "standalone_source" ]]; then
    run_standalone_static_gate_ci
    return
  fi
  local integrity_rc=0
  agentcanon_pr_branch_integrity
  integrity_rc=$?
  if [[ "$integrity_rc" -ne 0 ]]; then
    return 1
  fi
  if agentcanon_pr_branch_pending; then
    echo "AGENT_CANON_PR_LATEST_GATE=deferred_branch_pr"
    echo "AGENT_CANON_PR_LATEST_NEXT=commit_push_agentcanon_branch_then_after_merge_run_make_agent-canon-ensure-latest"
    run_direct_agent_checks
    return
  fi
  if [[ -f Makefile ]] && grep -qE "^[.]?PHONY:.*\\bagent-checks\\b|^agent-checks:" Makefile; then
    make agent-checks
  else
    bash tools/ci/check_agent_canon_latest.sh
    run_direct_agent_checks
  fi
}

run_pr_quick_ci() {
  if [[ "${AGENT_CANON_REPOSITORY_MODE}" == "standalone_source" ]]; then
    echo "AGENT_CANON_PR_QUICK_CI=consumed_standalone_static_gate_receipt"
    return
  fi
  local integrity_rc=0
  AGENT_CANON_PR_LATEST_GATE=""
  AGENT_CANON_PR_LATEST_NEXT=""
  agentcanon_pr_branch_integrity
  integrity_rc=$?
  if [[ "$integrity_rc" -ne 0 ]]; then
    echo "AGENT_CANON_PR_CI_LATEST_GATE=${AGENT_CANON_PR_LATEST_GATE:-blocked_submodule_integrity}"
    echo "AGENT_CANON_PR_CI_NEXT=${AGENT_CANON_PR_LATEST_NEXT:-repair_submodule_integrity_and_rerun_agent-canon-pr-check}"
    return 1
  fi
  if agentcanon_pr_branch_pending; then
    echo "AGENT_CANON_PR_CI_LATEST_GATE=deferred_branch_pr"
    echo "AGENT_CANON_PR_CI_COMMAND=bash tools/ci/run_all_checks.sh ${PR_QUICK_CI_ARGS[*]} --pr-gate-receipt ${PR_GATE_RECEIPT}"
    AGENT_CANON_CI_EVAL_LOG_DIR="${PR_RUN_ALL_CHECKS_LOG_DIR}" \
      bash tools/ci/run_all_checks.sh "${PR_QUICK_CI_ARGS[@]}" --pr-gate-receipt "${PR_GATE_RECEIPT}"
    return
  fi
  echo "AGENT_CANON_PR_CI_COMMAND=bash tools/ci/run_all_checks.sh ${PR_QUICK_CI_ARGS[*]} --pr-gate-receipt ${PR_GATE_RECEIPT}"
  AGENT_CANON_CI_EVAL_LOG_DIR="${PR_RUN_ALL_CHECKS_LOG_DIR}" \
    bash tools/ci/run_all_checks.sh "${PR_QUICK_CI_ARGS[@]}" --pr-gate-receipt "${PR_GATE_RECEIPT}"
}

write_pr_gate_receipt() {
  local root_identity=""
  if ! root_identity="$(realpath -e "${WORKSPACE_ROOT}")"; then
    echo "Unable to record PR gate root identity" >&2
    return 1
  fi
  {
    printf 'owner=check_agent_canon_pr.sh\n'
    printf 'root_identity=%s\n' "${root_identity}"
    printf 'parent_pid=%s\n' "$$"
    printf 'strict_dependency=prepared\n'
    printf 'graph=prepared\n'
  } >"${PR_GATE_RECEIPT}"
}

consume_source_correctness_receipt() {
  local bundle="${AGENT_CANON_PR_GATE_BUNDLE:-}"
  if [[ -z "${bundle}" ]]; then
    echo "AGENT_CANON_G1_RECEIPT=not_materialized_nontransaction"
    return
  fi
  PYTHONPATH="${PR_AGENT_CANON_SOURCE_ROOT}/tools/agent_tools${PYTHONPATH:+:${PYTHONPATH}}" \
    python3 - "${bundle}" <<'PY'
import json
import sys
from pathlib import Path
from update_lifecycle_contract import validate_gate_chain

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
    python3 "${PR_AGENT_CANON_SOURCE_ROOT}/tools/ci/check_agent_canon_pr.py"
    --g1-bundle "${bundle}"
    --source-root "${PR_AGENT_CANON_SOURCE_ROOT}"
  )
  if [[ "${AGENT_CANON_G1_BUNDLE_ACTIVE}" -ne 1 ]]; then
    echo "AGENT_CANON_G2_RECEIPT=not_materialized_nontransaction"
    return
  fi
  if [[ -n "${output}" ]]; then
    command+=(--output "${output}")
  fi
  "${command[@]}"
}

run_standalone_static_gate_ci() {
  cargo fmt --manifest-path rust/agent-canon/Cargo.toml -- --check
  cargo clippy --manifest-path rust/agent-canon/Cargo.toml --all-targets -- -D warnings
  cargo test --manifest-path rust/agent-canon/Cargo.toml
  python3 tools/agent_tools/tool_catalog.py
  python3 tools/agent_tools/tool_proof_coverage.py
  python3 tools/agent_tools/responsibility_scope.py
  BASE_REF="${GITHUB_BASE_REF:-main}"
  git fetch origin "${BASE_REF}" --depth=1 || true
  python3 tools/agent_tools/import_responsibility.py --changed --baseline-ref "origin/${BASE_REF}"
  python3 tools/agent_tools/issue_sync.py
  AGENT_CANON_HOOK_ARCHIVE_DIR="${PR_HOOK_ARCHIVE_DIR}" \
    python3 tools/agent_tools/run_accumulated_agent_evals.py --run-id agent-canon-pr-gate --log-dir "${PR_AGENT_EVAL_LOG_DIR}"
  AGENT_CANON_HOOK_ARCHIVE_DIR="${PR_HOOK_ARCHIVE_DIR}" \
    python3 tools/agent_tools/eval_accumulation_check.py
  python3 tools/agent_tools/check_agent_runtime_alignment.py
  python3 tools/agent_tools/smoke_test_research_perspective_pack.py
  python3 tools/agent_tools/check_convention_compliance.py
  python3 tools/agent_tools/skill_tool_commands.py check
  python3 tools/ci/check_github_workflows.py
  python3 tools/ci/container_config.py
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
echo "agent_canon_repository_mode=${AGENT_CANON_REPOSITORY_MODE}"
echo "agent_canon_remote=${REMOTE_URL}"
consume_source_correctness_receipt
if [[ "${AGENT_CANON_REPOSITORY_MODE}" == "template_or_derived" ]]; then
  echo "agent_canon_submodule_status=$(git submodule status vendor/agent-canon 2>/dev/null || true)"
  agent_canon_gitmodules_url="$(git config -f .gitmodules --get submodule.vendor/agent-canon.url 2>/dev/null || true)"
  agent_canon_submodule_mode="$(git ls-tree HEAD vendor/agent-canon 2>/dev/null | awk '{print $1}')"
  agent_canon_submodule_pin="$(git rev-parse HEAD:vendor/agent-canon 2>/dev/null || true)"
  echo "agent_canon_gitmodules_url=${agent_canon_gitmodules_url:-<missing>}"
  echo "agent_canon_submodule_mode=${agent_canon_submodule_mode:-<missing>}"
  echo "agent_canon_submodule_pin=${agent_canon_submodule_pin:-<missing>}"
  if [[ -z "$agent_canon_gitmodules_url" || "$agent_canon_submodule_mode" != "160000" || -z "$agent_canon_submodule_pin" ]]; then
    echo "AGENT_CANON_SUBMODULE_EVIDENCE=fail"
    exit 1
  fi
  echo "AGENT_CANON_SUBMODULE_EVIDENCE=pass"
else
  echo "agent_canon_submodule_status=<not_applicable>"
  echo "agent_canon_gitmodules_url=<not_applicable>"
  echo "agent_canon_submodule_mode=<not_applicable>"
  echo "agent_canon_submodule_pin=<not_applicable>"
  echo "AGENT_CANON_SUBMODULE_EVIDENCE=not_applicable_standalone_source"
fi
echo ""

echo "1️⃣  shared surface status"
run_shared_surface_status
echo ""

echo "2️⃣  shared surface drift check"
run_shared_surface_check
echo ""

echo "2b️⃣  GitHub workflow and PR template checks"
if [[ "${AGENT_CANON_REPOSITORY_MODE}" == "template_or_derived" ]]; then
  python3 tools/ci/check_github_workflows.py
else
  echo "GITHUB_WORKFLOW_CHECK=owned_by_standalone_static_gate"
fi
echo ""

echo "3️⃣  changed shared canon paths"
git status --short -- vendor/agent-canon .github/workflows/agent-coordination.yml .github/PULL_REQUEST_TEMPLATE/agent_canon.md || true
echo ""

echo "4️⃣  GitHub mirror and security evidence"
github_repo_security_status "${AGENT_CANON_GITHUB_REPO}" "agent_canon_github"
github_repo_security_status "${TEMPLATE_GITHUB_REPO}" "template_github"
echo ""

echo "5️⃣  agent runtime checks"
run_pr_agent_checks
echo ""

echo "6️⃣  strict dependency review"
# This graph build is the producer for the strict dependency review and the
# prepared graph consumers in the subsequent quick CI invocation.
tools/bin/agent-canon graph build --root . --profile default --format json
if [[ "${AGENT_CANON_REPOSITORY_MODE}" == "standalone_source" ]]; then
  python3 tools/agent_tools/tool_drift.py
fi
bash tools/agent_tools/run_repo_dependency_review.sh --fail-missing --cycle-report-only --report-dir "${PR_DEPENDENCY_REVIEW_DIR}"
python3 tools/agent_tools/render_dependency_manifest_graph.py \
  --root . \
  --scope full \
  --markdown-out "${PR_DEPENDENCY_REVIEW_DIR}/dependency_manifest_graph.md" \
  --dot-out "${PR_DEPENDENCY_REVIEW_DIR}/dependency_manifest_graph.dot"
write_pr_gate_receipt
echo ""

echo "7️⃣  documentation checks"
tools/bin/agent-canon docs check
echo ""

echo "8️⃣  repository quick CI"
run_pr_quick_ci
echo ""

echo "8b️⃣  generated artifact guard"
python3 tools/agent_tools/generated_artifact_guard.py --root "${WORKSPACE_ROOT}"
echo ""

emit_generated_completeness_receipt
echo ""

echo "AGENT_CANON_PR_CHECK=pass"
echo "AGENT_CANON_PR_PROPAGATION_WORKFLOW=agents/workflows/agent-canon-pr-workflow.md"
echo "NEXT_ACTION=Open_or_update_AgentCanon_PR_then_after_merge_run_make_agent-canon-ensure-latest_and_commit_template_pin"
