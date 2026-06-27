#!/usr/bin/env bash
# @dependency-start
# contract tool
# responsibility Checks agent canon pr CI readiness.
# upstream design ../../tools/README.md shared automation index
# upstream design ../../agents/workflows/agent-canon-pr-workflow.md shared canon PR workflow
# upstream design ../../.github/PULL_REQUEST_TEMPLATE.md standalone AgentCanon PR checklist
# upstream design ../../.github/PULL_REQUEST_TEMPLATE/agent_canon.md template AgentCanon PR checklist
# upstream implementation ../agent_tools/run_repo_dependency_review.sh strict dependency review
# upstream implementation ../agent_tools/evaluate_skill_workflow_prompts.py skill/workflow prompt parity eval
# upstream implementation ../agent_tools/run_accumulated_agent_evals.py writes required eval family reports before accumulation validation
# upstream implementation ../agent_tools/generated_artifact_guard.py rejects regenerated report leftovers before PR check pass
# upstream implementation ../agent_tools/check_agent_runtime_alignment.py Codex runtime role alignment eval
# upstream implementation ../agent_tools/check_convention_compliance.py convention gate wiring eval
# upstream implementation ../agent_tools/skill_tool_commands.py runtime skill command packet gate
# upstream implementation ./check_github_workflows.py GitHub workflow and PR template checks
# upstream implementation ./run_all_checks.sh quick CI implementation
# @dependency-end

set -euo pipefail

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
cleanup_agent_canon_pr_temp_root() {
  if [[ "${AGENT_CANON_PR_TEMP_ROOT_CREATED}" -eq 1 ]]; then
    rm -rf "${AGENT_CANON_PR_TEMP_ROOT}"
  fi
}
trap cleanup_agent_canon_pr_temp_root EXIT
PR_DEPENDENCY_REVIEW_DIR="${AGENT_CANON_PR_TEMP_ROOT}/dependency-review/agent-canon-pr"
PR_AGENT_EVAL_LOG_DIR="${AGENT_CANON_PR_TEMP_ROOT}/agent-eval-runs/agent-canon-pr-gate"
PR_RUN_ALL_CHECKS_LOG_DIR="${AGENT_CANON_PR_TEMP_ROOT}/agent-eval-runs/run-all-checks"
PR_QUICK_CI_ARGS=(--quick --skip-docs --skip-github-workflows)
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
  python3 tools/agent_tools/smoke_test_research_perspective_pack.py
  AGENT_CANON_HOOK_ARCHIVE_DIR="${PR_HOOK_ARCHIVE_DIR}" \
    python3 tools/agent_tools/evaluate_skill_workflow_prompts.py --manifest evidence/agent-evals/skill_workflow_prompt_eval.toml --accumulate
  python3 tools/agent_tools/check_convention_compliance.py
  python3 tools/agent_tools/skill_tool_commands.py check
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
    return 0
  fi
  git -C vendor/agent-canon fetch origin main >/dev/null 2>&1 || true
  remote_main="$(git -C vendor/agent-canon rev-parse origin/main 2>/dev/null || true)"
  if [[ -z "${remote_main}" || "${parent_pin}" != "${remote_main}" ]]; then
    return 0
  fi
  return 1
}

run_pr_agent_checks() {
  if [[ "${AGENT_CANON_REPOSITORY_MODE}" == "standalone_source" ]]; then
    run_direct_agent_checks
    return
  fi
  if agentcanon_pr_branch_dirty; then
    echo "AGENT_CANON_PR_LATEST_GATE=blocked_dirty_agentcanon_branch"
    echo "AGENT_CANON_PR_LATEST_NEXT=commit_agentcanon_artifacts_or_explicitly_stash_non_artifact_changes_then_rerun_agent-canon-pr-check"
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
    run_standalone_static_gate_ci
    return
  fi
  if agentcanon_pr_branch_dirty; then
    echo "AGENT_CANON_PR_CI_LATEST_GATE=blocked_dirty_agentcanon_branch"
    echo "AGENT_CANON_PR_CI_NEXT=commit_agentcanon_artifacts_or_explicitly_stash_non_artifact_changes_then_rerun_agent-canon-pr-check"
    return 1
  fi
  if agentcanon_pr_branch_pending; then
    echo "AGENT_CANON_PR_CI_LATEST_GATE=deferred_branch_pr"
    echo "AGENT_CANON_PR_CI_COMMAND=bash tools/ci/run_all_checks.sh ${PR_QUICK_CI_ARGS[*]}"
    AGENT_CANON_CI_EVAL_LOG_DIR="${PR_RUN_ALL_CHECKS_LOG_DIR}" bash tools/ci/run_all_checks.sh "${PR_QUICK_CI_ARGS[@]}"
    return
  fi
  echo "AGENT_CANON_PR_CI_COMMAND=bash tools/ci/run_all_checks.sh ${PR_QUICK_CI_ARGS[*]}"
  AGENT_CANON_CI_EVAL_LOG_DIR="${PR_RUN_ALL_CHECKS_LOG_DIR}" bash tools/ci/run_all_checks.sh "${PR_QUICK_CI_ARGS[@]}"
}

run_standalone_static_gate_ci() {
  cargo fmt --manifest-path rust/agent-canon/Cargo.toml -- --check
  cargo clippy --manifest-path rust/agent-canon/Cargo.toml --all-targets -- -D warnings
  cargo test --manifest-path rust/agent-canon/Cargo.toml
  python3 tools/agent_tools/tool_catalog.py
  python3 tools/agent_tools/tool_proof_coverage.py
  python3 tools/agent_tools/tool_drift.py
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
python3 tools/ci/check_github_workflows.py
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
bash tools/agent_tools/run_repo_dependency_review.sh --fail-missing --cycle-report-only --report-dir "${PR_DEPENDENCY_REVIEW_DIR}"
python3 tools/agent_tools/render_dependency_manifest_graph.py \
  --graph-tsv "${PR_DEPENDENCY_REVIEW_DIR}/dependency_graph.tsv" \
  --markdown-out "${PR_DEPENDENCY_REVIEW_DIR}/dependency_manifest_graph.md" \
  --dot-out "${PR_DEPENDENCY_REVIEW_DIR}/dependency_manifest_graph.dot"
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

echo "AGENT_CANON_PR_CHECK=pass"
echo "AGENT_CANON_PR_PROPAGATION_WORKFLOW=agents/workflows/agent-canon-pr-workflow.md"
echo "NEXT_ACTION=Open_or_update_AgentCanon_PR_then_after_merge_run_make_agent-canon-ensure-latest_and_commit_template_pin"
