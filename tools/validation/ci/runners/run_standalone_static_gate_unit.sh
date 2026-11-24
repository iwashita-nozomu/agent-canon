#!/usr/bin/env bash
# @dependency-start
# contract tool
# responsibility Runs one standalone AgentCanon static-gate execution unit without selecting whether that unit is required.
# upstream design ../../../../documents/runtime/runtime-profiles-and-check-matrix.md risk-based validation routing
# upstream implementation ./run_all_checks.sh owns the full-confidence check body
# upstream implementation ../../../../tools/runtime/dispatch/agent-canon/src/eval_archive_paths.rs resolves the canonical eval archive destination
# upstream implementation ../../../../tools/runtime/dispatch/agent-canon/src/eval_accumulation_check.rs validates accumulated hook and eval results
# downstream implementation ../checks/check_agent_canon_pr.sh aggregates all units for the manual full-confidence route
# downstream implementation ../../../../.github/workflows/agent-canon-static-gates.yml remote execution boundary
# downstream implementation ../../../../tests/tools/test_standalone_static_gate_units.py unit partition regression
# downstream implementation ../../../../tests/tools/test_read_only_full_check.py read-only full-check regression
# downstream implementation ../../../../tests/tools/test_standalone_static_gate_source_runtime_contract.py source/runtime ownership regression
# @dependency-end

set -euo pipefail

if [[ "$#" -lt 1 ]]; then
  echo "usage: $0 {docs|rust|contracts|eval|workflow-container|full} [docs-paths|full-check-options...]" >&2
  exit 2
fi

UNIT="$1"
shift
UNIT_ARGS=("$@")
if [[ "${UNIT}" != "full" && "${UNIT}" != "docs" && "${UNIT}" != "rust" && "${#UNIT_ARGS[@]}" -ne 0 ]]; then
  echo "standalone static-gate unit does not accept arguments: ${UNIT}" >&2
  exit 2
fi

SCRIPT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd -P)"
ROOT="${AGENT_CANON_TARGET_ROOT:-${SCRIPT_ROOT}}"
default_cli=agent-canon
if [[ -n "${AGENT_CANON_CACHE_ROOT:-}" ]]; then
  default_cli="${AGENT_CANON_CACHE_ROOT}/bin/agent-canon"
fi
export AGENT_CANON_CLI="${AGENT_CANON_NATIVE_BIN:-${AGENT_CANON_CLI:-${default_cli}}}"
export AGENT_CANON_NATIVE_BIN="${AGENT_CANON_CLI}"
cd "${ROOT}"
ROOT="$(pwd -P)"

# Runtime artifacts belong to the caller-selected external runtime root.  Keep
# the path resolver in runtime_boundary.rs as the single source of truth.
runtime_boundary_root() {
  "${AGENT_CANON_CLI}" runtime-paths root --source-root "${ROOT}" --runtime-root "$1"
}

runtime_boundary_path() {
  "${AGENT_CANON_CLI}" runtime-paths path --source-root "${ROOT}" --runtime-root "${AGENT_CANON_STATIC_RUNTIME_ROOT}" --candidate "$1"
}

if [[ "${UNIT}" != docs || -n "${AGENT_CANON_RUNTIME_ROOT:-}" ]]; then
  AGENT_CANON_STATIC_RUNTIME_ROOT="$(runtime_boundary_root "${AGENT_CANON_RUNTIME_ROOT:-}")"
  export AGENT_CANON_RUNTIME_ROOT="${AGENT_CANON_STATIC_RUNTIME_ROOT}"
  TMPDIR="$(runtime_boundary_path "${TMPDIR:-${AGENT_CANON_STATIC_RUNTIME_ROOT}/tmp}")"
  XDG_CACHE_HOME="$(runtime_boundary_path "${AGENT_CANON_STATIC_RUNTIME_ROOT}/cache")"
  export TMPDIR XDG_CACHE_HOME
  mkdir -p "${TMPDIR}" "${XDG_CACHE_HOME}"
fi
export PYTHONDONTWRITEBYTECODE=1

run_full() {
  # Bootstrap authenticates and supplies this control capability.  The
  # runtime root is an exchange location, not a parent-root authority.
  local control_parent_root="${AGENT_CANON_CONTROL_PARENT_ROOT:?AGENT_CANON_CONTROL_PARENT_ROOT is required}"
  AGENT_CANON_CONTROL_PARENT_ROOT="${control_parent_root}" \
  AGENT_CANON_CHILD_PURPOSE="standalone-static-gate-unit" \
  AGENT_CANON_CLI_CMD="${AGENT_CANON_CLI}" \
  AGENT_CANON_RUNTIME_ROOT="${AGENT_CANON_STATIC_RUNTIME_ROOT}" \
    bash "${ROOT}/tools/validation/ci/runners/run_all_checks.sh" "${UNIT_ARGS[@]}"
}

run_docs() {
  local path
  local -a paths=()
  for path in "${UNIT_ARGS[@]}"; do
    # A deletion can break links in unchanged documents. Use the docs owner's
    # full check rather than silently dropping missing input paths.
    if [[ ! -f "${ROOT}/${path#./}" ]]; then
      "${AGENT_CANON_CLI}" docs check --root "${ROOT}"
      return
    fi
    paths+=("./${path#./}")
  done
  "${AGENT_CANON_CLI}" docs check --root "${ROOT}" "${paths[@]}"
}

run_rust() {
  # Producer identity checks hash the test executable; reduce debug-only bytes.
  export CARGO_PROFILE_TEST_DEBUG=0
  export CARGO_TARGET_DIR="${CARGO_TARGET_DIR:-${AGENT_CANON_STATIC_RUNTIME_ROOT}/cargo-target}"
  local phase="${1:-all}"
  case "${phase}" in
    controller-driver)
      [[ "$#" -eq 1 ]] || return 2
      cargo build --manifest-path tools/runtime/dispatch/agent-canon/Cargo.toml --locked --offline --features controller-test-driver \
        --bin agent-canon-controller-test-driver
      ;;
    all|prepare)
      [[ "$#" -le 1 ]] || return 2
      cargo build --manifest-path tools/runtime/dispatch/agent-canon/Cargo.toml --locked --offline
      cargo fmt --manifest-path tools/runtime/dispatch/agent-canon/Cargo.toml -- --check
      cargo clippy --manifest-path tools/runtime/dispatch/agent-canon/Cargo.toml --locked --offline --all-targets -- -D warnings
      if [[ "${phase}" == "prepare" ]]; then
        cargo test --manifest-path tools/runtime/dispatch/agent-canon/Cargo.toml --locked --offline --no-run
      else
        env -u AGENT_CANON_RUNTIME_ROOT \
          cargo test --manifest-path tools/runtime/dispatch/agent-canon/Cargo.toml --locked --offline
      fi
      ;;
    lib|doc)
      [[ "$#" -eq 1 ]] || return 2
      env -u AGENT_CANON_RUNTIME_ROOT \
        cargo test --manifest-path tools/runtime/dispatch/agent-canon/Cargo.toml --locked --offline "--${phase}"
      ;;
    bin|test)
      [[ "$#" -eq 2 ]] || return 2
      env -u AGENT_CANON_RUNTIME_ROOT \
        cargo test --manifest-path tools/runtime/dispatch/agent-canon/Cargo.toml --locked --offline "--${phase}" "$2"
      ;;
    *) echo "unknown Rust validation phase: ${phase}" >&2; return 2 ;;
  esac
}

run_contracts() {
  python3 -m pytest -p no:cacheprovider --pyargs \
    tests.agent_tools.test_tool_dispatch \
    tests.agent_tools.test_paper_writing_citeproc \
    tests.agent_tools.test_render_dependency_manifest_graph \
    tests.agent_tools.test_graph_client_source_projection \
    tests.agent_tools.test_search \
    tests.tools.test_notebook_quality \
    tests.tools.test_docs_link_inputs \
    tests.agent_tools.test_check_solid_evidence \
    tests.agent_tools.test_check_semantic_responsibility_contract \
    tests.agent_tools.test_check_run_log_contract \
    tests.agent_tools.test_structured_document_inventory_cli \
    tests.agent_tools.test_classify_path_risk \
    tests.tools.test_standalone_static_gate_source_runtime_contract \
    tests.agent_tools.test_check_convention_compliance \
    tests.agent_tools.test_check_dependency_headers \
    tests.agent_tools.test_check_algorithm_config_partition \
    tests.agent_tools.test_tool_drift \
    tests/agent_tools/test_dependency_*.py
  python3 -m pytest -p no:cacheprovider -q tests/agent_tools/test_evaluate_agent_run.py
  python3 -m pytest -p no:cacheprovider \
    tests/agent_tools/test_prose_reasoning_graph.py::ProseReasoningGraphTest::test_check_document_preserves_missing_manifest_severity
  "${AGENT_CANON_CLI}" tool-catalog
  "${AGENT_CANON_CLI}" tool-proof-coverage
  "${AGENT_CANON_CLI}" responsibility-scope --root "${ROOT}"
  "${AGENT_CANON_CLI}" check-agent-runtime-alignment --root "${ROOT}"
  "${AGENT_CANON_CLI}" check-convention-compliance \
    --root "${ROOT}" --format json
}

run_eval() (
  local temp_root eval_results_parent primary_status=0 cleanup_status=0
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
  # Create the canonical archive's eval-results directory for CI readback,
  # using the archive owner's path resolver rather than a caller override.
  local eval_log_dir="${temp_root}/agent-eval-runs/agent-canon-pr-gate"
  eval_results_parent="${AGENT_CANON_STATIC_RUNTIME_ROOT}/archive/agent-canon-log/eval-results"
  mkdir -p "${eval_log_dir}" "${eval_results_parent}"
  env -u AGENT_CANON_HOOK_ARCHIVE_DIR -u AGENT_CANON_LOG_ROOT \
    python3 -m pytest -p no:cacheprovider -q \
      tests/agent_tools/test_eval_accumulation_check.py \
      tests/agent_tools/test_evaluate_codex_agent_roles.py \
      tests/agent_tools/test_model_profile_registry.py
  set +e
  env -u AGENT_CANON_HOOK_ARCHIVE_DIR -u AGENT_CANON_LOG_ROOT \
    "${AGENT_CANON_CLI}" run-accumulated-agent-evals \
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
    env -u AGENT_CANON_HOOK_ARCHIVE_DIR -u AGENT_CANON_LOG_ROOT \
      "${AGENT_CANON_CLI}" eval-accumulation-check \
        --root "${ROOT}" --runtime-root "${AGENT_CANON_STATIC_RUNTIME_ROOT}"
    primary_status=$?
  fi
  set -e
  return "${primary_status}"
)

run_workflow_container() {
  local controller_test_driver
  run_rust controller-driver
  controller_test_driver="${CARGO_TARGET_DIR}/debug/agent-canon-controller-test-driver"
  AGENT_CANON_CONTROLLER_TEST_DRIVER="${controller_test_driver}" \
  python3 -m pytest -p no:cacheprovider -q \
    tests/tools/test_standalone_static_gate_units.py \
    tests/tools/test_read_only_full_check.py \
    tests/tools/test_check_github_workflows.py \
    tests/tools/test_agent_improvement_guide_workflow.py
  "${AGENT_CANON_CLI}" check-github-workflows --root "${ROOT}"
  AGENT_CANON_CONTROLLER_TEST_DRIVER="${controller_test_driver}" \
  python3 -m pytest -p no:cacheprovider -q \
    tests/tools/test_bootstrap_container_contract.py \
    tests/tools/test_compile_cache.py
}

case "${UNIT}" in
  full) run_full ;;
  docs) run_docs ;;
  rust) run_rust "${UNIT_ARGS[@]}" ;;
  contracts) run_contracts ;;
  eval) run_eval ;;
  workflow-container) run_workflow_container ;;
  *)
    echo "unknown standalone static-gate unit: ${UNIT}" >&2
    exit 2
    ;;
esac

echo "AGENT_CANON_STATIC_GATE_UNIT=${UNIT} status=pass"
