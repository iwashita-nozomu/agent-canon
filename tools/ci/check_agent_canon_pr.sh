#!/usr/bin/env bash
# @dependency-start
# upstream design ../README.md shared automation index
# @dependency-end

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
WORKSPACE_ROOT="$(git -C "${SCRIPT_DIR}" rev-parse --show-toplevel)"
cd "${WORKSPACE_ROOT}"

REMOTE_NAME="${AGENT_CANON_REMOTE_NAME:-agent-canon}"
REMOTE_URL="<unset>"
if git remote get-url "${REMOTE_NAME}" >/dev/null 2>&1; then
  REMOTE_URL="$(git remote get-url "${REMOTE_NAME}")"
fi

echo "=========================================="
echo "AGENT-CANON PR CHECK"
echo "=========================================="
echo "workspace_root=${WORKSPACE_ROOT}"
echo "agent_canon_remote=${REMOTE_URL}"
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

echo "4️⃣  agent runtime checks"
make agent-checks
echo ""

echo "5️⃣  documentation checks"
make docs-check
echo ""

echo "6️⃣  repository quick CI"
make ci-quick
echo ""

echo "AGENT_CANON_PR_CHECK=pass"
echo "NEXT_ACTION=Open_or_update_agent-canon_PR_then_merge_and_run_bash_tools/sync_agent_canon.sh_push"
