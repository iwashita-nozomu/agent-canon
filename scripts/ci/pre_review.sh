#!/bin/bash

# pre_review.sh — PR 前の自動 QA チェック
#
# 使用方法:
#   scripts/ci/pre_review.sh
#
# このスクリプトは以下を実行します:
#   1. Type checking (Pyright strict mode)
#   2. Test execution (pytest)
#   3. Docstring validation (pydocstyle)
#   4. Code quality checks (Ruff)
#
# 環境要件: Python 3.10+, pyright, pytest, pydocstyle, ruff がインストール済み

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
cd "${WORKSPACE_ROOT}"

export PYTHONPATH="${WORKSPACE_ROOT}/python:${PYTHONPATH:-}"
export JAX_PLATFORMS="${JAX_PLATFORMS:-cpu}"
export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-}"
export NVIDIA_VISIBLE_DEVICES="${NVIDIA_VISIBLE_DEVICES:-}"

REPORT_DIR="${AGENT_REPORT_DIR:-}"
REPORT_FILE=""
REPORT_SNAPSHOT_FILE=""
WORKSPACE_SNAPSHOT_FILE=""
RUN_STATUS="running"
AGENT_ROLE_NAME="${AGENT_ROLE:-}"
ENFORCE_WRITE_SCOPE="${AGENT_ENFORCE_WRITE_SCOPE:-0}"
if [ -n "${REPORT_DIR}" ]; then
    mkdir -p "${REPORT_DIR}"
    if [ -n "${AGENT_ROLE_NAME}" ] && [ "${ENFORCE_WRITE_SCOPE}" = "1" ]; then
        REPORT_SNAPSHOT_FILE="$(mktemp)"
        WORKSPACE_SNAPSHOT_FILE="$(mktemp)"
        python3 scripts/agent_tools/validate_role_write_scope.py \
            --report-dir "${REPORT_DIR}" \
            --workspace-root "${WORKSPACE_ROOT}" \
            --report-snapshot-out "${REPORT_SNAPSHOT_FILE}" \
            --workspace-snapshot-out "${WORKSPACE_SNAPSHOT_FILE}" > /dev/null
    fi
    REPORT_FILE="${REPORT_DIR%/}/verification.txt"
    {
        echo "pre_review_started_at_utc=$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
        echo "workspace_root=${WORKSPACE_ROOT}"
    } > "${REPORT_FILE}"
fi

# 色定義
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

write_report() {
    if [ -n "${REPORT_FILE}" ]; then
        echo "$1" >> "${REPORT_FILE}"
    fi
}

enforce_write_scope() {
    if [ -z "${REPORT_DIR}" ] || [ -z "${AGENT_ROLE_NAME}" ] || [ "${ENFORCE_WRITE_SCOPE}" != "1" ]; then
        return 0
    fi
    local cmd=(
        python3
        scripts/agent_tools/validate_role_write_scope.py
        --role "${AGENT_ROLE_NAME}"
        --report-dir "${REPORT_DIR}"
        --workspace-root "${WORKSPACE_ROOT}"
    )
    if [ -n "${REPORT_FILE}" ]; then
        cmd+=(--file "${REPORT_FILE}")
    fi
    if [ -n "${REPORT_SNAPSHOT_FILE}" ]; then
        cmd+=(--report-snapshot-in "${REPORT_SNAPSHOT_FILE}")
    fi
    if [ -n "${WORKSPACE_SNAPSHOT_FILE}" ]; then
        cmd+=(--workspace-snapshot-in "${WORKSPACE_SNAPSHOT_FILE}")
    fi
    if "${cmd[@]}"; then
        write_report "write_scope=pass"
        return 0
    fi
    write_report "write_scope=fail"
    return 1
}

fail_run() {
    RUN_STATUS="failed"
    enforce_write_scope || true
    exit 1
}

finalize_report() {
    write_report "status=${RUN_STATUS}"
    write_report "pre_review_finished_at_utc=$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
    if [ -n "${REPORT_SNAPSHOT_FILE}" ] && [ -f "${REPORT_SNAPSHOT_FILE}" ]; then
        rm -f "${REPORT_SNAPSHOT_FILE}"
    fi
    if [ -n "${WORKSPACE_SNAPSHOT_FILE}" ] && [ -f "${WORKSPACE_SNAPSHOT_FILE}" ]; then
        rm -f "${WORKSPACE_SNAPSHOT_FILE}"
    fi
}

trap finalize_report EXIT

echo ""
echo "=========================================="
echo "PRE-REVIEW QA CHECKS"
echo "=========================================="
echo "JAX test platform: ${JAX_PLATFORMS}"

if [ -f "${WORKSPACE_ROOT}/WORKTREE_SCOPE.md" ]; then
    echo ""
    echo -e "${BLUE}0️⃣  Worktree scope / action-log checks...${NC}"
    if python3 scripts/agent_tools/worktree_scope_lint.py --current; then
        echo -e "${GREEN}✅ Worktree scope / action-log checks passed${NC}"
        write_report "worktree_scope=pass"
    else
        echo -e "${RED}❌ Worktree scope / action-log checks failed. Refresh WORKTREE_SCOPE.md and the action log.${NC}"
        write_report "worktree_scope=fail"
        fail_run
    fi
fi

# 1. Type checking
echo ""
echo -e "${BLUE}1️⃣  Type Checking (Pyright strict mode)...${NC}"
if python3 -m pyright; then
    echo -e "${GREEN}✅ Type checking passed${NC}"
    write_report "pyright=pass"
else
    echo -e "${RED}❌ Type errors found. Review code.${NC}"
    write_report "pyright=fail"
    fail_run
fi

# 2. Test execution
echo ""
echo -e "${BLUE}2️⃣  Running pytest...${NC}"
if python3 -m pytest tests/ -q --tb=short; then
    echo -e "${GREEN}✅ All tests passed${NC}"
    write_report "pytest=pass"
else
    echo -e "${RED}❌ Test failures. Fix tests.${NC}"
    write_report "pytest=fail"
    fail_run
fi

# 3. Docstring validation
echo ""
echo -e "${BLUE}3️⃣  Docstring validation (pydocstyle)...${NC}"
if python3 -m pydocstyle python tests; then
    echo -e "${GREEN}✅ Docstring validation passed${NC}"
    write_report "pydocstyle=pass"
else
    echo -e "${YELLOW}⚠️  Docstring issues. Review output above.${NC}"
    write_report "pydocstyle=warn"
fi

# 4. Code quality
echo ""
echo -e "${BLUE}4️⃣  Code quality checks (Ruff)...${NC}"
if python3 -m ruff check python tests --select E,F,I,D,UP; then
    echo -e "${GREEN}✅ Code quality checks passed${NC}"
    write_report "ruff=pass"
else
    echo -e "${YELLOW}⚠️  Style issues found. Review output above.${NC}"
    write_report "ruff=warn"
fi

echo ""
echo "=========================================="
echo -e "${GREEN}✅ PRE-REVIEW CHECKS COMPLETE${NC}"
echo "=========================================="
echo ""
echo "Next: Commit changes and open PR"
echo ""
RUN_STATUS="passed"
if ! enforce_write_scope; then
    RUN_STATUS="failed"
    echo -e "${RED}❌ Write scope violation detected for role ${AGENT_ROLE_NAME}.${NC}"
    exit 1
fi
