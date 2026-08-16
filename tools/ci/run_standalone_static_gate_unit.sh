#!/usr/bin/env bash
# @dependency-start
# contract tool
# responsibility Runs one standalone AgentCanon static-gate execution unit without selecting whether that unit is required.
# upstream design ../../documents/runtime/runtime-profiles-and-check-matrix.md risk-based validation routing
# upstream implementation ./run_with_fixture_record.py owns the unit-level private fixture record bootstrap
# downstream implementation ./check_agent_canon_pr.sh aggregates all units for the manual full-confidence route
# downstream implementation ../../.github/workflows/agent-canon-static-gates.yml remote execution boundary
# downstream implementation ../../tests/tools/test_standalone_static_gate_units.py unit partition regression
# downstream implementation ../../tests/tools/test_standalone_static_gate_source_runtime_contract.py source/runtime ownership regression
# downstream implementation ../../tests/tools/test_standalone_static_gate_record_bootstrap.py record-bootstrap regression
# downstream implementation ../../tests/tools/test_runtime_alignment_fixture_boundary.py runtime-alignment fixture-owner regression
# @dependency-end

set -euo pipefail

if [[ "$#" -ne 1 ]]; then
  echo "usage: $0 {rust|contracts|eval|workflow-container}" >&2
  exit 2
fi

UNIT="$1"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
source "${SCRIPT_DIR}/../lib/repo_paths.sh"
ROOT="$(agent_canon_repo_root "${BASH_SOURCE[0]}")"
TOOLS_ROOT="$(agent_canon_source_tools_root "${ROOT}")"
cd "${ROOT}"

if [[ "${AGENT_CANON_SIDE_EFFECT_SESSION_REQUIRED:-}" != "1" \
   || -z "${AGENT_CANON_SIDE_EFFECT_PARENT_ROOT:-}" \
   || -z "${AGENT_CANON_SIDE_EFFECT_HANDOFF:-}" \
   || "${AGENT_CANON_PRIVATE_RECORD_REQUIRED:-}" != "1" \
   || -z "${AGENT_CANON_PRIVATE_RECORD_PARENT_ROOT:-}" \
   || -z "${AGENT_CANON_PRIVATE_RECORD_HANDOFF:-}" ]]; then
  invocation_script="$(realpath -e "${BASH_SOURCE[0]}" 2>/dev/null || true)"
  if [[ -z "${invocation_script}" || ! -f "${invocation_script}" ]]; then
    echo "STANDALONE_STATIC_GATE=fail reason=invocation_script_missing" >&2
    exit 2
  fi
  exec python3 "${TOOLS_ROOT}/ci/run_with_fixture_record.py" \
    --invocation-script "${invocation_script}" \
    --purpose standalone-static-gate-unit \
    -- bash "${invocation_script}" "$UNIT"
fi

run_rust() {
  cargo build --manifest-path rust/agent-canon/Cargo.toml
  local memory_cli="${CARGO_TARGET_DIR:?}/debug/agent-canon"
  if [[ ! -x "${memory_cli}" ]]; then
    echo "AGENT_CANON_MEMORY_CLI_BUILD=fail" >&2
    return 1
  fi
  "${memory_cli}" memory validate --root .
  cargo fmt --manifest-path rust/agent-canon/Cargo.toml -- --check
  cargo clippy --manifest-path rust/agent-canon/Cargo.toml --all-targets -- -D warnings
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
    tests.tools.test_standalone_static_gate_record_bootstrap \
    tests.tools.test_runtime_alignment_fixture_boundary \
    tests.agent_tools.test_check_dependency_headers \
    tests.agent_tools.test_check_design_doc_claims \
    tests.agent_tools.test_tool_drift \
    tests.agent_tools.test_vector_search \
    tests.agent_tools.test_dependency_manifest_tools
  python3 "${TOOLS_ROOT}/agent_tools/tool_catalog.py"
  python3 "${TOOLS_ROOT}/agent_tools/tool_proof_coverage.py"
  python3 "${TOOLS_ROOT}/agent_tools/responsibility_scope.py"
  local base_ref="${GITHUB_BASE_REF:-main}"
  git fetch origin "${base_ref}" --depth=1 || true
  python3 "${TOOLS_ROOT}/agent_tools/import_responsibility.py" \
    --changed --baseline-ref "origin/${base_ref}"
  python3 "${TOOLS_ROOT}/agent_tools/issue_sync.py"
  python3 "${TOOLS_ROOT}/agent_tools/check_agent_runtime_alignment.py"
  python3 "${TOOLS_ROOT}/agent_tools/check_convention_compliance.py" \
    --root "${ROOT}" --format json
  python3 "${TOOLS_ROOT}/agent_tools/skill_tool_commands.py" check
}

run_eval() (
  local temp_root primary_status=0 cleanup_status=0
  temp_root="$(python3 "${TOOLS_ROOT}/agent_tools/parent_root_side_effects.py" temp-dir \
    --root "${ROOT}" --candidate "${ROOT}/.agent-canon/tmp" \
    --prefix "agent-canon-static-eval" --purpose "standalone-static-eval")"
  cleanup_eval() {
    local trap_status=$?
    trap - EXIT
    set +e
    python3 "${TOOLS_ROOT}/agent_tools/parent_root_side_effects.py" remove-tree \
      --root "${ROOT}" --candidate "${temp_root}" \
      --purpose "standalone-static-eval-cleanup" >/dev/null
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
  local hook_archive="${AGENT_CANON_HOOK_ARCHIVE_DIR:-${ROOT}/.agent-canon/log-archive}"
  local eval_log_dir="${temp_root}/agent-eval-runs/agent-canon-pr-gate"
  hook_archive="$(python3 "${TOOLS_ROOT}/agent_tools/parent_root_side_effects.py" ensure-dir \
    --root "${ROOT}" --candidate "${hook_archive}" --purpose "standalone-static-eval-hook-archive")"
  eval_log_dir="$(python3 "${TOOLS_ROOT}/agent_tools/parent_root_side_effects.py" ensure-dir \
    --root "${ROOT}" --candidate "${eval_log_dir}" --purpose "standalone-static-eval-log-dir")"
  set +e
  AGENT_CANON_HOOK_ARCHIVE_DIR="${hook_archive}" \
    python3 "${TOOLS_ROOT}/agent_tools/run_accumulated_agent_evals.py" \
      --run-id agent-canon-pr-gate \
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
      python3 "${TOOLS_ROOT}/agent_tools/eval_accumulation_check.py"
    primary_status=$?
  fi
  if [[ "${primary_status}" -eq 0 ]]; then
    python3 "${TOOLS_ROOT}/agent_tools/smoke_test_research_perspective_pack.py"
    primary_status=$?
  fi
  set -e
  return "${primary_status}"
)

run_workflow_container() {
  python3 -m pytest tests/tools/test_standalone_static_gate_units.py -q
  python3 "${TOOLS_ROOT}/ci/check_github_workflows.py"
  python3 "${TOOLS_ROOT}/ci/container_config.py"
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
