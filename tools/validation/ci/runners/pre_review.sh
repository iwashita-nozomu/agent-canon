#!/usr/bin/env bash
# @dependency-start
# contract tool
# responsibility Runs verifier pre-review checks through the shared Python quality runner.
# upstream design ../../../README.md shared automation index
# upstream implementation ../checks/run_python_quality_checks.sh shared Python quality gate
# upstream implementation ../../../runtime/dispatch/agent-canon/src/runtime_boundary.rs owns external report paths and exact cleanup
# @dependency-end
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_ROOT="$(cd "${SCRIPT_DIR}/../../../.." && pwd)"
cd "${WORKSPACE_ROOT}"

# Reports and snapshots are runtime artifacts, not source files.  Resolve all
# paths through the shared Rust runtime boundary and retain only a task
# namespace under the caller-owned external root.
runtime_boundary_root() {
  "${AGENT_CANON_NATIVE_BIN:-${AGENT_CANON_CLI:-${WORKSPACE_ROOT}/tools/bin/agent-canon}}" runtime-paths root --source-root "${WORKSPACE_ROOT}" --runtime-root "$1"
}

runtime_boundary_path() {
  "${AGENT_CANON_NATIVE_BIN:-${AGENT_CANON_CLI:-${WORKSPACE_ROOT}/tools/bin/agent-canon}}" runtime-paths path --source-root "${WORKSPACE_ROOT}" --runtime-root "${AGENT_CANON_RUNTIME_ROOT}" --candidate "$1"
}

if [ -n "${AGENT_CANON_RUNTIME_ROOT:-}" ]; then
  AGENT_CANON_RUNTIME_ROOT_PRESET=1
  AGENT_CANON_PRE_REVIEW_RUNTIME_ROOT="${AGENT_CANON_RUNTIME_ROOT}"
else
  AGENT_CANON_RUNTIME_ROOT_PRESET=0
  AGENT_CANON_PRE_REVIEW_RUNTIME_ROOT="${RUNNER_TEMP:-${TMPDIR:-/tmp}}/agent-canon-pre-review-${PPID}-${BASHPID}"
fi
AGENT_CANON_RUNTIME_ROOT="$(runtime_boundary_root "${AGENT_CANON_PRE_REVIEW_RUNTIME_ROOT}")"
export AGENT_CANON_RUNTIME_ROOT
export AGENT_CANON_CONTROL_PARENT_ROOT="${AGENT_CANON_CONTROL_PARENT_ROOT:-${WORKSPACE_ROOT}}"
export TMPDIR="$(runtime_boundary_path "${AGENT_CANON_RUNTIME_ROOT}/tmp")"
mkdir -p "${TMPDIR}"

REPORT_DIR="${AGENT_REPORT_DIR:-}"
REPORT_FILE=""
REPORT_CONTENT=""
RUN_STATUS="running"

if [ -n "${REPORT_DIR}" ]; then
  REPORT_DIR="$(runtime_boundary_path "${REPORT_DIR}")"
  mkdir -p "${REPORT_DIR}"
  REPORT_FILE="${REPORT_DIR%/}/verification.txt"
fi

write_report() {
  if [ -n "${REPORT_FILE}" ]; then
    REPORT_CONTENT+="$1"$'\n'
    printf '%s' "${REPORT_CONTENT}" > "${REPORT_FILE}"
  fi
}

if [ -n "${REPORT_FILE}" ]; then
  write_report "pre_review_started_at_utc=$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
  write_report "workspace_root=${WORKSPACE_ROOT}"
  write_report "python_quality_runner=tools/validation/ci/checks/run_python_quality_checks.sh"
fi

finalize_report() {
  local status=$?
  local cleanup_status=0
  write_report "status=${RUN_STATUS}"
  write_report "pre_review_finished_at_utc=$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
  if [ "${AGENT_CANON_RUNTIME_ROOT_PRESET}" -eq 0 ]; then
    rm -rf -- "${AGENT_CANON_RUNTIME_ROOT}" || cleanup_status=$?
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

if bash tools/validation/ci/checks/run_python_quality_checks.sh "$@"; then
  write_report "python_quality=pass"
else
  RUN_STATUS="failed"
  write_report "python_quality=fail"
  exit 1
fi

RUN_STATUS="passed"
echo "PRE_REVIEW=pass"
