#!/usr/bin/env bash
# @dependency-start
# contract tool
# responsibility Runs one standalone AgentCanon static-gate execution unit without selecting whether that unit is required.
# upstream design ../../documents/runtime/runtime-profiles-and-check-matrix.md risk-based validation routing
# downstream implementation ./check_agent_canon_pr.sh aggregates all units for the manual full-confidence route
# downstream implementation ../../.github/workflows/agent-canon-static-gates.yml remote execution boundary
# downstream implementation ../../tests/tools/test_standalone_static_gate_units.py unit partition regression
# downstream implementation ../../tests/tools/test_standalone_static_gate_source_runtime_contract.py source/runtime ownership regression
# @dependency-end

set -euo pipefail

if [[ "$#" -ne 1 ]]; then
  echo "usage: $0 {rust|contracts|eval|workflow-container}" >&2
  exit 2
fi

UNIT="$1"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
if [[ ! -f /usr/local/share/agent-canon/.agent-canon-tool-container ]]; then
  echo "AGENT_CANON_STATIC_GATE=fail reason=shared_tool_runtime_required" >&2
  exit 2
fi
ROOT="${AGENT_CANON_TARGET_ROOT:?AGENT_CANON_TARGET_ROOT is required}"
TOOLS_ROOT=/usr/local/share/agent-canon/runtime/tools
cd "${ROOT}"

# Runtime artifacts belong to the caller-selected external runtime root.  Keep
# the path resolver in runtime_artifacts.py as the single source of truth.
runtime_boundary_root() {
  local candidate="$1"
  PYTHONPATH="${TOOLS_ROOT}/agent_tools${PYTHONPATH:+:${PYTHONPATH}}" \
    python3 - "${ROOT}" "${candidate}" <<'PY'
from pathlib import Path
import sys

from runtime_artifacts import runtime_artifact_boundary

source_root = Path(sys.argv[1])
runtime_root = Path(sys.argv[2])
print(runtime_artifact_boundary(source_root, runtime_root, create=True).root)
PY
}

runtime_boundary_path() {
  local candidate="$1"
  PYTHONPATH="${TOOLS_ROOT}/agent_tools${PYTHONPATH:+:${PYTHONPATH}}" \
    python3 - "${ROOT}" "${AGENT_CANON_STATIC_RUNTIME_ROOT}" "${candidate}" <<'PY'
from pathlib import Path
import sys

from runtime_artifacts import runtime_artifact_boundary

boundary = runtime_artifact_boundary(Path(sys.argv[1]), Path(sys.argv[2]), create=True)
print(boundary.resolve(Path(sys.argv[3])))
PY
}

AGENT_CANON_STATIC_RUNTIME_ROOT="${AGENT_CANON_RUNTIME_ROOT}"
AGENT_CANON_STATIC_RUNTIME_ROOT="$(runtime_boundary_root "${AGENT_CANON_STATIC_RUNTIME_ROOT}")"
export AGENT_CANON_RUNTIME_ROOT="${AGENT_CANON_STATIC_RUNTIME_ROOT}"
export AGENT_CANON_CACHE_ROOT="$(runtime_boundary_path "${AGENT_CANON_CACHE_ROOT:-${AGENT_CANON_STATIC_RUNTIME_ROOT}/cache}")"
export CARGO_TARGET_DIR="$(runtime_boundary_path "${CARGO_TARGET_DIR:-${AGENT_CANON_CACHE_ROOT}/cargo-target}")"
export TMPDIR="$(runtime_boundary_path "${TMPDIR:-${AGENT_CANON_STATIC_RUNTIME_ROOT}/tmp}")"
mkdir -p "${CARGO_TARGET_DIR}" "${TMPDIR}"

run_rust() {
  cargo build --manifest-path rust/agent-canon/Cargo.toml
  local agent_cli="${CARGO_TARGET_DIR:?}/debug/agent-canon"
  if [[ ! -x "${agent_cli}" ]]; then
    echo "AGENT_CANON_CLI_BUILD=fail" >&2
    return 1
  fi
  "${agent_cli}" --version
  cargo fmt --manifest-path rust/agent-canon/Cargo.toml -- --check
  cargo clippy --manifest-path rust/agent-canon/Cargo.toml --all-targets -- -D warnings
  env -u AGENT_CANON_RUNTIME_ROOT \
    cargo test --manifest-path rust/agent-canon/Cargo.toml
}

run_contracts() {
  node --version
  python3 -m unittest \
    tests.agent_tools.test_visualization_contract \
    tests.agent_tools.test_render_dependency_manifest_graph \
    tests.agent_tools.test_graph_client_source_projection \
    tests.tools.test_agent_canon_pr_dependency_source_gate \
    tests.tools.test_agent_canon_pr_graph_gate_integration \
    tests.tools.test_standalone_static_gate_source_runtime_contract \
    tests.agent_tools.test_source_root_failure_lifecycle \
    tests.agent_tools.test_check_dependency_headers \
    tests.agent_tools.test_check_design_doc_claims \
    tests.agent_tools.test_tool_drift \
    tests.agent_tools.test_vector_search \
    tests.agent_tools.test_dependency_manifest_tools
  python3 "${TOOLS_ROOT}/agent_tools/tool_catalog.py"
  python3 "${TOOLS_ROOT}/agent_tools/tool_proof_coverage.py"
  python3 "${TOOLS_ROOT}/agent_tools/responsibility_scope.py"
  local base_ref="${GITHUB_BASE_REF:-main}"
  git rev-parse --verify "origin/${base_ref}^{commit}" >/dev/null
  python3 "${TOOLS_ROOT}/agent_tools/import_responsibility.py" \
    --changed --baseline-ref "origin/${base_ref}"
  PYTHONPATH="${ROOT}/tools/agent_tools${PYTHONPATH:+:${PYTHONPATH}}" \
    python3 "${ROOT}/tools/agent_tools/check_agent_runtime_alignment.py"
  python3 "${TOOLS_ROOT}/agent_tools/check_convention_compliance.py" \
    --root "${ROOT}" --format json
  python3 "${TOOLS_ROOT}/agent_tools/skill_tool_commands.py" check
}

run_eval() (
  local temp_root primary_status=0 cleanup_status=0
  temp_root="${AGENT_CANON_STATIC_RUNTIME_ROOT}/eval/agent-canon-pr-gate"
  mkdir -p "${temp_root}"
  cleanup_eval() {
    local trap_status=$?
    trap - EXIT
    set +e
    rm -rf -- "${temp_root}"
    cleanup_status=$?
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
  local hook_archive="${AGENT_CANON_HOOK_ARCHIVE_DIR:-${AGENT_CANON_STATIC_RUNTIME_ROOT}/archive/agent-canon-log}"
  local eval_log_dir="${temp_root}/agent-eval-runs/agent-canon-pr-gate"
  hook_archive="$(runtime_boundary_path "${hook_archive}")"
  mkdir -p "${eval_log_dir}"
  set +e
  AGENT_CANON_HOOK_ARCHIVE_DIR="${hook_archive}" \
    python3 "${TOOLS_ROOT}/agent_tools/run_accumulated_agent_evals.py" \
      --run-id agent-canon-pr-gate \
      --root "${ROOT}" \
      --runtime-root "${AGENT_CANON_STATIC_RUNTIME_ROOT}" \
      --log-dir "${eval_log_dir}" \
      --skill-used agent-orchestration \
      --skill-used result-artifact-writeout
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
    AGENT_CANON_HOOK_ARCHIVE_DIR="${hook_archive}" \
      python3 "${TOOLS_ROOT}/agent_tools/eval_accumulation_check.py" \
        --root "${ROOT}" --runtime-root "${AGENT_CANON_STATIC_RUNTIME_ROOT}"
    primary_status=$?
  fi
  if [[ "${primary_status}" -eq 0 ]]; then
    PYTHONPATH="${ROOT}/tools/agent_tools${PYTHONPATH:+:${PYTHONPATH}}" \
      python3 "${ROOT}/tools/agent_tools/smoke_test_research_perspective_pack.py"
    primary_status=$?
  fi
  set -e
  return "${primary_status}"
)

run_workflow_container() {
  python3 -m pytest -p no:cacheprovider tests/tools/test_standalone_static_gate_units.py -q
  python3 "${ROOT}/tools/ci/check_github_workflows.py"
  python3 -m pytest -p no:cacheprovider -q \
    tests/tools/test_bootstrap_container_contract.py \
    tests/bootstrap/test_bootstrap_runtime.py
}

case "${UNIT}" in
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
