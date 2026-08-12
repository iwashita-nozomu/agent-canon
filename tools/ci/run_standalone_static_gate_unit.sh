#!/usr/bin/env bash
# @dependency-start
# contract tool
# responsibility Runs one standalone AgentCanon static-gate execution unit without selecting whether that unit is required.
# upstream design ../../documents/runtime/runtime-profiles-and-check-matrix.md risk-based validation routing
# upstream implementation ./check_agent_canon_pr.sh existing full standalone static-gate command set
# downstream implementation ../../.github/workflows/agent-canon-static-gates.yml remote execution boundary
# downstream test ../../tests/tools/test_standalone_static_gate_units.py unit partition regression
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

run_rust() {
  cargo build --manifest-path rust/agent-canon/Cargo.toml
  local memory_cli="${ROOT}/rust/agent-canon/target/debug/agent-canon"
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

run_eval() {
  local temp_root
  temp_root="$(mktemp -d "${TMPDIR:-/tmp}/agent-canon-static-eval.XXXXXX")"
  trap 'rm -rf "${temp_root}"' RETURN
  local hook_archive="${AGENT_CANON_HOOK_ARCHIVE_DIR:-${ROOT}/.agent-canon/log-archive}"
  local eval_log_dir="${temp_root}/agent-eval-runs/agent-canon-pr-gate"
  mkdir -p "${hook_archive}" "${eval_log_dir}"
  AGENT_CANON_HOOK_ARCHIVE_DIR="${hook_archive}" \
    python3 "${TOOLS_ROOT}/agent_tools/run_accumulated_agent_evals.py" \
      --run-id agent-canon-pr-gate --log-dir "${eval_log_dir}"
  AGENT_CANON_HOOK_ARCHIVE_DIR="${hook_archive}" \
    python3 "${TOOLS_ROOT}/agent_tools/eval_accumulation_check.py"
  python3 "${TOOLS_ROOT}/agent_tools/smoke_test_research_perspective_pack.py"
}

run_workflow_container() {
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
