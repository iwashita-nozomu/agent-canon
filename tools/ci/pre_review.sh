#!/usr/bin/env bash
# @dependency-start
# contract tool
# responsibility Runs verifier pre-review checks through the shared Python quality runner.
# upstream design ../README.md shared automation index
# upstream implementation ./run_python_quality_checks.sh shared Python quality gate
# upstream implementation ../agent_tools/runtime_artifacts.py owns external report paths and exact cleanup
# @dependency-end
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
cd "${WORKSPACE_ROOT}"

# Reports and snapshots are runtime artifacts, not source files.  Resolve all
# paths through the shared Python runtime boundary and retain only a task
# namespace under the caller-owned external root.
runtime_boundary_root() {
  local candidate="$1"
  PYTHONPATH="${WORKSPACE_ROOT}/tools/agent_tools${PYTHONPATH:+:${PYTHONPATH}}" \
    python3 - "${WORKSPACE_ROOT}" "${candidate}" <<'PY'
from pathlib import Path
import sys

from runtime_artifacts import runtime_artifact_boundary

print(runtime_artifact_boundary(Path(sys.argv[1]), Path(sys.argv[2]), create=True).root)
PY
}

runtime_boundary_path() {
  local candidate="$1"
  PYTHONPATH="${WORKSPACE_ROOT}/tools/agent_tools${PYTHONPATH:+:${PYTHONPATH}}" \
    python3 - "${WORKSPACE_ROOT}" "${AGENT_CANON_RUNTIME_ROOT}" "${candidate}" <<'PY'
from pathlib import Path
import sys

from runtime_artifacts import runtime_artifact_boundary

boundary = runtime_artifact_boundary(Path(sys.argv[1]), Path(sys.argv[2]), create=True)
print(boundary.resolve(Path(sys.argv[3])))
PY
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
REPORT_SNAPSHOT_FILE=""
WORKSPACE_SNAPSHOT_FILE=""
TEMP_DIR=""
RUN_STATUS="running"
AGENT_ROLE_NAME="${AGENT_ROLE:-}"
ENFORCE_WRITE_SCOPE="${AGENT_ENFORCE_WRITE_SCOPE:-0}"

if [ -n "${REPORT_DIR}" ]; then
  REPORT_DIR="$(runtime_boundary_path "${REPORT_DIR}")"
  mkdir -p "${REPORT_DIR}"
  if [ -n "${AGENT_ROLE_NAME}" ] && [ "${ENFORCE_WRITE_SCOPE}" = "1" ]; then
    TEMP_DIR="$(runtime_boundary_path "${AGENT_CANON_RUNTIME_ROOT}/tasks/pre-review-${BASHPID}")"
    mkdir -p "${TEMP_DIR}"
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
    printf '%s' "${REPORT_CONTENT}" > "${REPORT_FILE}"
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
    rm -rf -- "${TEMP_DIR}" || cleanup_status=$?
  fi
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
