#!/usr/bin/env bash
# @dependency-start
# contract tool
# responsibility Runs one standalone AgentCanon static-gate execution unit without selecting whether that unit is required.
# upstream design ../../../../documents/runtime/runtime-profiles-and-check-matrix.md risk-based validation routing
# upstream implementation ./run_all_checks.sh owns the full-confidence check body executed from a read-only target
# downstream implementation ../checks/check_agent_canon_pr.sh aggregates all units for the manual full-confidence route
# downstream implementation ../../../../.github/workflows/agent-canon-static-gates.yml remote execution boundary
# downstream implementation ../../../../tests/tools/test_standalone_static_gate_units.py unit partition regression
# downstream implementation ../../../../tests/tools/test_read_only_full_check.py read-only full-check regression
# downstream implementation ../../../../tests/tools/test_standalone_static_gate_source_runtime_contract.py source/runtime ownership regression
# @dependency-end

set -euo pipefail

if [[ "$#" -lt 1 ]]; then
  echo "usage: $0 {docs|rust|contracts|eval|workflow-container|full} [docs-paths|contracts-baseline|full-check-options...]" >&2
  exit 2
fi

UNIT="$1"
shift
UNIT_ARGS=("$@")
if [[ "${UNIT}" != "full" && "${UNIT}" != "docs" && "${UNIT}" != "contracts" && "${#UNIT_ARGS[@]}" -ne 0 ]] ||
   [[ "${UNIT}" == "contracts" && "${#UNIT_ARGS[@]}" -gt 1 ]]; then
  echo "standalone static-gate unit does not accept arguments: ${UNIT}" >&2
  exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
if [[ ! -f /usr/local/share/agent-canon/.agent-canon-tool-container ]]; then
  echo "AGENT_CANON_STATIC_GATE=fail reason=shared_tool_runtime_required" >&2
  exit 2
fi
ROOT="${AGENT_CANON_TARGET_ROOT:?AGENT_CANON_TARGET_ROOT is required}"
RUNTIME_ROOT="$(cd "${SCRIPT_DIR}/../../../.." && pwd -P)"
TOOLS_ROOT="${RUNTIME_ROOT}/tools"

assert_read_only_target() {
  python3 - "${ROOT}" <<'PY'
import json
from pathlib import Path
import subprocess
import sys


# libmount owns path decoding, nested mounts and visible overmount selection.
# Query this process's namespace; only VFS flags authorize the read-only body.
try:
    target = Path(sys.argv[1]).resolve(strict=True)
    result = subprocess.run(
        [
            "findmnt", "--kernel", "--first-only", "--direction", "backward",
            "--list", "--target", str(target), "--json",
            "--output", "TARGET,VFS-OPTIONS",
        ],
        check=True, capture_output=True, text=True,
    )
    payload = json.loads(result.stdout)
except (OSError, subprocess.CalledProcessError, ValueError) as error:
    raise SystemExit(
        f"AGENT_CANON_STATIC_GATE=fail reason=target_mount_query_failed error={type(error).__name__}"
    ) from error

mounts = payload.get("filesystems") if isinstance(payload, dict) else None
if not isinstance(mounts, list) or len(mounts) != 1 or not isinstance(mounts[0], dict):
    raise SystemExit("AGENT_CANON_STATIC_GATE=fail reason=target_mount_missing")
mount_point = mounts[0].get("target")
vfs_options = mounts[0].get("vfs-options")
if not isinstance(mount_point, str) or not mount_point or not isinstance(vfs_options, str):
    raise SystemExit("AGENT_CANON_STATIC_GATE=fail reason=target_mount_columns_missing")
options = set(vfs_options.split(","))
if "ro" not in options or "rw" in options:
    raise SystemExit(
        f"AGENT_CANON_STATIC_GATE=fail reason=target_mount_not_read_only mount={mount_point}"
    )
print(f"AGENT_CANON_STATIC_GATE_TARGET_MOUNT=read-only mount={mount_point}")
PY
}

assert_read_only_target
cd "${ROOT}"

# Runtime artifacts belong to the caller-selected external runtime root.  Keep
# the path resolver in runtime_artifacts.py as the single source of truth.
runtime_boundary_root() {
  local candidate="$1"
  PYTHONPATH="${RUNTIME_ROOT}${PYTHONPATH:+:${PYTHONPATH}}" \
    python3 - "${ROOT}" "${candidate}" <<'PY'
from pathlib import Path
import sys

from tools.runtime.artifacts.runtime_artifacts import runtime_artifact_boundary

source_root = Path(sys.argv[1])
runtime_root = Path(sys.argv[2])
print(runtime_artifact_boundary(source_root, runtime_root, create=True).root)
PY
}

runtime_boundary_path() {
  local candidate="$1"
  PYTHONPATH="${RUNTIME_ROOT}${PYTHONPATH:+:${PYTHONPATH}}" \
    python3 - "${ROOT}" "${AGENT_CANON_STATIC_RUNTIME_ROOT}" "${candidate}" <<'PY'
from pathlib import Path
import sys

from tools.runtime.artifacts.runtime_artifacts import runtime_artifact_boundary

boundary = runtime_artifact_boundary(Path(sys.argv[1]), Path(sys.argv[2]), create=True)
print(boundary.resolve(Path(sys.argv[3])))
PY
}

AGENT_CANON_STATIC_RUNTIME_ROOT="${AGENT_CANON_RUNTIME_ROOT}"
AGENT_CANON_STATIC_RUNTIME_ROOT="$(runtime_boundary_root "${AGENT_CANON_STATIC_RUNTIME_ROOT}")"
export AGENT_CANON_RUNTIME_ROOT="${AGENT_CANON_STATIC_RUNTIME_ROOT}"
export TMPDIR="$(runtime_boundary_path "${TMPDIR:-${AGENT_CANON_STATIC_RUNTIME_ROOT}/tmp}")"
mkdir -p "${TMPDIR}"
export PYTHONDONTWRITEBYTECODE=1

run_full() {
  # Bootstrap authenticates and supplies this control capability.  The
  # runtime root is an exchange location, not a parent-root authority.
  local control_parent_root="${AGENT_CANON_CONTROL_PARENT_ROOT:?AGENT_CANON_CONTROL_PARENT_ROOT is required}"
  AGENT_CANON_CONTROL_PARENT_ROOT="${control_parent_root}" \
  AGENT_CANON_CHILD_PURPOSE="standalone-static-gate-unit" \
  AGENT_CANON_CLI_CMD="${AGENT_CANON_CACHE_ROOT}/bin/agent-canon" \
  AGENT_CANON_RUNTIME_ROOT="${AGENT_CANON_STATIC_RUNTIME_ROOT}" \
    bash "${ROOT}/tools/validation/ci/runners/run_all_checks.sh" "${UNIT_ARGS[@]}"
}

run_docs() {
  local cli="${AGENT_CANON_CACHE_ROOT}/bin/agent-canon"
  local path
  local -a paths=()
  for path in "${UNIT_ARGS[@]}"; do
    # A deletion can break links in unchanged documents. Use the docs owner's
    # full check rather than silently dropping missing input paths.
    if [[ ! -f "${ROOT}/${path#./}" ]]; then
      "${cli}" docs check --root "${ROOT}"
      return
    fi
    paths+=("./${path#./}")
  done
  "${cli}" docs check --root "${ROOT}" "${paths[@]}"
}

run_rust() {
  cargo build --manifest-path tools/runtime/dispatch/agent-canon/Cargo.toml
  local agent_cli="${CARGO_TARGET_DIR:?}/debug/agent-canon"
  if [[ ! -x "${agent_cli}" ]]; then
    echo "AGENT_CANON_CLI_BUILD=fail" >&2
    return 1
  fi
  "${agent_cli}" --version
  cargo fmt --manifest-path tools/runtime/dispatch/agent-canon/Cargo.toml -- --check
  cargo clippy --manifest-path tools/runtime/dispatch/agent-canon/Cargo.toml --all-targets -- -D warnings
  env -u AGENT_CANON_RUNTIME_ROOT \
    cargo test --manifest-path tools/runtime/dispatch/agent-canon/Cargo.toml
}

run_contracts() {
  node --version
  python3 -m pytest -p no:cacheprovider --pyargs \
    tests.agent_tools.test_visualization_contract \
    tests.agent_tools.test_render_dependency_manifest_graph \
    tests.agent_tools.test_graph_client_source_projection \
    tests.agent_tools.test_structured_document_inventory_cli \
    tests.tools.test_standalone_static_gate_source_runtime_contract \
    tests.agent_tools.test_source_root_failure_lifecycle \
    tests.agent_tools.test_check_dependency_headers \
    tests.agent_tools.test_check_design_doc_claims \
    tests.agent_tools.test_tool_drift \
    tests.agent_tools.test_vector_search \
    tests/agent_tools/test_dependency_*.py
  python3 -m pytest -p no:cacheprovider \
    tests/agent_tools/test_prose_reasoning_graph.py::ProseReasoningGraphTest::test_missing_dependency_annotation_is_not_a_blocker
  python3 "${TOOLS_ROOT}/runtime/manifest/tool_catalog.py"
  python3 "${TOOLS_ROOT}/analysis/proof/tool_proof_coverage.py"
  python3 "${TOOLS_ROOT}/validation/semantic/responsibility/responsibility_scope.py"
  PYTHONPATH="${ROOT}${PYTHONPATH:+:${PYTHONPATH}}" \
    python3 "${ROOT}/tools/validation/semantic/runtime/check_agent_runtime_alignment.py"
  python3 "${TOOLS_ROOT}/validation/semantic/convention/check_convention_compliance.py" \
    --root "${ROOT}" --format json
}

run_eval() (
  local temp_root primary_status=0 cleanup_status=0
  temp_root="${AGENT_CANON_STATIC_RUNTIME_ROOT}/eval/agent-canon-pr-gate"
  mkdir -p "${temp_root}"
  cleanup_eval() {
    local trap_status=$?
    trap - EXIT
    set +e
    # CI copies failed producer logs from the runtime volume before teardown.
    if [[ "${primary_status}" -eq 0 && "${trap_status}" -eq 0 ]]; then
      rm -rf -- "${temp_root}"
      cleanup_status=$?
    fi
    set -e
    if [[ "${primary_status}" -ne 0 ]]; then
      exit "${primary_status}"
    fi
    if [[ "${trap_status}" -ne 0 ]]; then
      exit "${trap_status}"
    fi
    exit "${cleanup_status}"
  }
  trap cleanup_eval EXIT
  # Static evaluations use the CI runtime root, not the shared private hook log.
  local eval_archive_root="${AGENT_CANON_STATIC_RUNTIME_ROOT}"
  local eval_log_dir="${temp_root}/agent-eval-runs/agent-canon-pr-gate"
  mkdir -p "${eval_log_dir}" "${eval_archive_root}/eval-results"
  set +e
  AGENT_CANON_HOOK_ARCHIVE_DIR="${eval_archive_root}" \
  AGENT_CANON_LOG_ROOT="${eval_archive_root}" \
    python3 "${RUNTIME_ROOT}/eval/producers/run_accumulated_agent_evals.py" \
      --run-id agent-canon-pr-gate \
      --root "${ROOT}" \
      --runtime-root "${AGENT_CANON_STATIC_RUNTIME_ROOT}" \
      --log-dir "${eval_log_dir}"
  primary_status=$?
  if [[ "${primary_status}" -ne 0 ]]; then
    local eval_log
    for eval_log in "${eval_log_dir}"/*.stdout.txt "${eval_log_dir}"/*.stderr.txt; do
      [[ -f "${eval_log}" && -s "${eval_log}" ]] || continue
      printf 'AGENT_CANON_STATIC_EVAL_LOG_BEGIN=%s\n' "$(basename "${eval_log}")"
      sed -n '1,160p' "${eval_log}"
      printf 'AGENT_CANON_STATIC_EVAL_LOG_END=%s\n' "$(basename "${eval_log}")"
      if grep -Eq 'status=fail|_STATUS=fail|_FAILED=[1-9][0-9]*' "${eval_log}"; then
        printf 'AGENT_CANON_STATIC_EVAL_FAILURE_LINES_BEGIN=%s\n' "$(basename "${eval_log}")"
        grep -E 'status=fail|_STATUS=fail|_FAILED=[1-9][0-9]*' "${eval_log}" | sed -n '1,160p'
        printf 'AGENT_CANON_STATIC_EVAL_FAILURE_LINES_END=%s\n' "$(basename "${eval_log}")"
      fi
    done
  fi
  if [[ "${primary_status}" -eq 0 ]]; then
    AGENT_CANON_HOOK_ARCHIVE_DIR="${eval_archive_root}" \
    AGENT_CANON_LOG_ROOT="${eval_archive_root}" \
      python3 "${RUNTIME_ROOT}/eval/checkers/eval_accumulation_check.py" \
        --root "${ROOT}" --runtime-root "${AGENT_CANON_STATIC_RUNTIME_ROOT}"
    primary_status=$?
  fi
  if [[ "${primary_status}" -eq 0 ]]; then
    PYTHONPATH="${ROOT}${PYTHONPATH:+:${PYTHONPATH}}" \
      python3 "${ROOT}/eval/checkers/smoke_test_research_perspective_pack.py"
    primary_status=$?
  fi
  set -e
  return "${primary_status}"
)

run_workflow_container() {
  python3 -m pytest -p no:cacheprovider -q \
    tests/tools/test_standalone_static_gate_units.py \
    tests/tools/test_read_only_full_check.py
  python3 "${ROOT}/tools/validation/ci/checks/check_github_workflows.py"
  python3 -m pytest -p no:cacheprovider -q \
    tests/tools/test_bootstrap_container_contract.py \
    tests/bootstrap/test_bootstrap_runtime.py
}

case "${UNIT}" in
  full) run_full ;;
  docs) run_docs ;;
  rust) run_rust ;;
  contracts) run_contracts ;;
  eval) run_eval ;;
  workflow-container) run_workflow_container ;;
  *)
    echo "unknown standalone static-gate unit: ${UNIT}" >&2
    exit 2
    ;;
esac

echo "AGENT_CANON_STATIC_GATE_UNIT=${UNIT} status=pass"
