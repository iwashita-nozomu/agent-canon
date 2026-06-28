#!/usr/bin/env bash
# @dependency-start
# contract tool
# responsibility Runs verifier pre-review checks through the shared Python quality runner.
# upstream design ../README.md shared automation index
# upstream implementation ./run_python_quality_checks.sh shared Python quality gate
# downstream implementation ../../.github/workflows/agent-coordination.yml verifier stage calls this entrypoint
# @dependency-end
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
cd "${WORKSPACE_ROOT}"

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
    python3 tools/agent_tools/validate_role_write_scope.py \
      --report-dir "${REPORT_DIR}" \
      --workspace-root "${WORKSPACE_ROOT}" \
      --report-snapshot-out "${REPORT_SNAPSHOT_FILE}" \
      --workspace-snapshot-out "${WORKSPACE_SNAPSHOT_FILE}" >/dev/null
  fi
  REPORT_FILE="${REPORT_DIR%/}/verification.txt"
  {
    echo "pre_review_started_at_utc=$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
    echo "workspace_root=${WORKSPACE_ROOT}"
    echo "python_quality_runner=tools/ci/run_python_quality_checks.sh"
  } >"${REPORT_FILE}"
fi

write_report() {
  if [ -n "${REPORT_FILE}" ]; then
    echo "$1" >>"${REPORT_FILE}"
  fi
}

enforce_write_scope() {
  if [ -z "${REPORT_DIR}" ] || [ -z "${AGENT_ROLE_NAME}" ] || [ "${ENFORCE_WRITE_SCOPE}" != "1" ]; then
    return 0
  fi
  local cmd=(
    python3
    tools/agent_tools/validate_role_write_scope.py
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
echo "PRE-REVIEW PYTHON QUALITY CHECKS"
echo "=========================================="

if bash tools/ci/run_python_quality_checks.sh "$@"; then
  write_report "python_quality=pass"
else
  RUN_STATUS="failed"
  write_report "python_quality=fail"
  enforce_write_scope || true
  exit 1
fi

if ! enforce_write_scope; then
  RUN_STATUS="failed"
  echo "write_scope=fail role=${AGENT_ROLE_NAME}" >&2
  exit 1
fi

RUN_STATUS="passed"
echo "PRE_REVIEW=pass"
