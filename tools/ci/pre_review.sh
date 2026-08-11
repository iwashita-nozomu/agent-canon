#!/usr/bin/env bash
# @dependency-start
# contract tool
# responsibility Runs verifier pre-review checks through the shared Python quality runner.
# upstream design ../README.md shared automation index
# upstream implementation ./run_python_quality_checks.sh shared Python quality gate
# upstream implementation ../agent_tools/parent_root_side_effects.py owns report paths, child state, and exact cleanup
# downstream implementation ../../.github/workflows/agent-coordination.yml verifier stage calls this entrypoint
# downstream implementation ../../tests/tools/test_pre_review.py verifies report publication and child environment containment
# @dependency-end
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
cd "${WORKSPACE_ROOT}"
BOUNDARY_SCRIPT="${WORKSPACE_ROOT}/tools/agent_tools/parent_root_side_effects.py"

REPORT_DIR="${AGENT_REPORT_DIR:-}"
REPORT_FILE=""
REPORT_CONTENT=""
REPORT_SNAPSHOT_FILE=""
WORKSPACE_SNAPSHOT_FILE=""
TEMP_DIR=""
RUN_STATUS="running"
AGENT_ROLE_NAME="${AGENT_ROLE:-}"
ENFORCE_WRITE_SCOPE="${AGENT_ENFORCE_WRITE_SCOPE:-0}"

if [ -n "${REPORT_DIR}" ]; then
  REPORT_DIR="$(
    python3 "${BOUNDARY_SCRIPT}" ensure-dir \
      --root "${WORKSPACE_ROOT}" \
      --candidate "${REPORT_DIR}" \
      --purpose pre-review-report
  )"
  if [ -n "${AGENT_ROLE_NAME}" ] && [ "${ENFORCE_WRITE_SCOPE}" = "1" ]; then
    TEMP_DIR="$(
      python3 "${BOUNDARY_SCRIPT}" temp-dir \
        --root "${WORKSPACE_ROOT}" \
        --candidate "${WORKSPACE_ROOT}/.agent-canon/tmp" \
        --prefix pre-review. \
        --purpose pre-review-snapshots
    )"
    REPORT_SNAPSHOT_FILE="${TEMP_DIR}/report.json"
    WORKSPACE_SNAPSHOT_FILE="${TEMP_DIR}/workspace.json"
    python3 tools/agent_tools/validate_role_write_scope.py \
      --report-dir "${REPORT_DIR}" \
      --workspace-root "${WORKSPACE_ROOT}" \
      --report-snapshot-out "${REPORT_SNAPSHOT_FILE}" \
      --workspace-snapshot-out "${WORKSPACE_SNAPSHOT_FILE}" >/dev/null
  fi
  REPORT_FILE="${REPORT_DIR%/}/verification.txt"
fi

write_report() {
  if [ -n "${REPORT_FILE}" ]; then
    REPORT_CONTENT+="$1"$'\n'
    printf '%s' "${REPORT_CONTENT}" | python3 "${BOUNDARY_SCRIPT}" write \
      --root "${WORKSPACE_ROOT}" \
      --candidate "${REPORT_FILE}" \
      --purpose pre-review-report-content >/dev/null
  fi
}

if [ -n "${REPORT_FILE}" ]; then
  write_report "pre_review_started_at_utc=$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
  write_report "workspace_root=${WORKSPACE_ROOT}"
  write_report "python_quality_runner=tools/ci/run_python_quality_checks.sh"
fi

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
  local status=$?
  local cleanup_status=0
  write_report "status=${RUN_STATUS}"
  write_report "pre_review_finished_at_utc=$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
  if [ -n "${TEMP_DIR}" ]; then
    python3 "${BOUNDARY_SCRIPT}" remove-tree \
      --root "${WORKSPACE_ROOT}" \
      --candidate "${TEMP_DIR}" \
      --purpose pre-review-cleanup >/dev/null || cleanup_status=$?
  fi
  if [ "$status" -eq 0 ] && [ "$cleanup_status" -ne 0 ]; then
    status=$cleanup_status
  fi
  return "$status"
}

trap finalize_report EXIT

echo ""
echo "=========================================="
echo "PRE-REVIEW PYTHON QUALITY CHECKS"
echo "=========================================="

if python3 "${BOUNDARY_SCRIPT}" exec-parent-bound \
  --root "${WORKSPACE_ROOT}" \
  --purpose pre-review-python-quality \
  -- bash tools/ci/run_python_quality_checks.sh "$@"; then
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
