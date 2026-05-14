#!/usr/bin/env bash
# @dependency-start
# responsibility Checks agent canon pr CI readiness.
# upstream design ../../tools/README.md shared automation index
# upstream design ../../agents/workflows/agent-canon-pr-workflow.md shared canon PR workflow
# upstream design ../../.github/PULL_REQUEST_TEMPLATE.md standalone AgentCanon PR checklist
# upstream design ../../.github/PULL_REQUEST_TEMPLATE/agent_canon.md template AgentCanon PR checklist
# upstream implementation ../agent_tools/run_repo_dependency_review.sh strict dependency review
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

run_make_or_direct() {
  local target="$1"
  shift
  if [[ -f Makefile ]] && grep -qE "^[.]?PHONY:.*\\b${target}\\b|^${target}:" Makefile; then
    make "${target}"
  else
    "$@"
  fi
}

run_direct_agent_checks() {
  bash tools/sync_agent_canon.sh check
  python3 tools/docs/mirror_skill_shims.py --target .claude/skills --prune --check
  python3 tools/agent_tools/check_agent_runtime_alignment.py
  python3 tools/agent_tools/smoke_test_research_perspective_pack.py
}

agentcanon_pr_branch_pending() {
  local submodule_dirty=""
  local submodule_head=""
  local parent_pin=""
  if [[ "${AGENT_CANON_REPOSITORY_MODE}" != "template_or_derived" ]]; then
    return 1
  fi
  submodule_dirty="$(git -C vendor/agent-canon status --short --untracked-files=all 2>/dev/null || true)"
  if [[ -n "${submodule_dirty}" ]]; then
    return 0
  fi
  submodule_head="$(git -C vendor/agent-canon rev-parse HEAD 2>/dev/null || true)"
  parent_pin="$(git rev-parse HEAD:vendor/agent-canon 2>/dev/null || true)"
  [[ -n "${submodule_head}" && -n "${parent_pin}" && "${submodule_head}" != "${parent_pin}" ]]
}

run_pr_agent_checks() {
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
  if agentcanon_pr_branch_pending; then
    echo "AGENT_CANON_PR_CI_LATEST_GATE=deferred_branch_pr"
    echo "AGENT_CANON_PR_CI_COMMAND=bash tools/ci/run_all_checks.sh --quick"
    bash tools/ci/run_all_checks.sh --quick
    return
  fi
  run_make_or_direct ci-quick bash tools/ci/run_all_checks.sh --quick
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
bash tools/sync_agent_canon.sh status
echo ""

echo "2️⃣  shared surface drift check"
bash tools/sync_agent_canon.sh check
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
bash tools/agent_tools/run_repo_dependency_review.sh --fail-missing
echo ""

echo "7️⃣  documentation checks"
run_make_or_direct docs-check bash tools/ci/run_docs_checks.sh
echo ""

echo "8️⃣  repository quick CI"
run_pr_quick_ci
echo ""

echo "AGENT_CANON_PR_CHECK=pass"
echo "AGENT_CANON_PR_PROPAGATION_WORKFLOW=agents/workflows/agent-canon-pr-workflow.md"
echo "NEXT_ACTION=Open_or_update_AgentCanon_PR_then_after_merge_run_make_agent-canon-ensure-latest_and_commit_template_pin"
