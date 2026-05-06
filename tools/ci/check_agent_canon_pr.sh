#!/usr/bin/env bash
# @dependency-start
# responsibility Checks agent canon pr CI readiness.
# upstream design ../README.md shared automation index
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
echo "agent_canon_remote=${REMOTE_URL}"
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
echo ""

echo "1️⃣  shared surface status"
bash tools/sync_agent_canon.sh status
echo ""

echo "2️⃣  shared surface drift check"
bash tools/sync_agent_canon.sh check
echo ""

echo "3️⃣  changed shared canon paths"
git status --short -- vendor/agent-canon .github/workflows/agent-coordination.yml .github/PULL_REQUEST_TEMPLATE/agent_canon.md || true
echo ""

echo "4️⃣  GitHub mirror and security evidence"
github_repo_security_status "${AGENT_CANON_GITHUB_REPO}" "agent_canon_github"
github_repo_security_status "${TEMPLATE_GITHUB_REPO}" "template_github"
echo ""

echo "5️⃣  agent runtime checks"
make agent-checks
echo ""

echo "6️⃣  documentation checks"
make docs-check
echo ""

echo "7️⃣  repository quick CI"
make ci-quick
echo ""

echo "AGENT_CANON_PR_CHECK=pass"
echo "NEXT_ACTION=Open_or_update_agent-canon_PR_then_merge_and_run_bash_tools/sync_agent_canon.sh_push"
