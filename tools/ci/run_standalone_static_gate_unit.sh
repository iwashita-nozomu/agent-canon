#!/usr/bin/env bash
# @dependency-start
# contract tool
# responsibility Runs one standalone AgentCanon static-gate execution unit without selecting whether that unit is required.
# upstream design ../../documents/runtime/runtime-profiles-and-check-matrix.md risk-based validation routing
# downstream implementation ./check_agent_canon_pr.sh aggregates all units for the manual full-confidence route
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

run_pr_670_validation() {
  local -a changed_paths=(
    documents/agent-canon/clean-detached-parent-update.md
    tests/agent_tools/test_attach_clean_detached_submodule.py
    tools/agent_tools/attach_clean_detached_submodule.py
    tools/update_agent_canon.sh
  )

  python3 -m pip install --upgrade pytest ruff pyright
  python3 -m pytest -q tests/agent_tools/test_attach_clean_detached_submodule.py
  python3 -m pytest -q tests/tools/test_update_agent_canon.py
  python3 -m ruff check \
    tools/agent_tools/attach_clean_detached_submodule.py \
    tests/agent_tools/test_attach_clean_detached_submodule.py
  PYTHONPATH=tools/agent_tools python3 -m pyright \
    tools/agent_tools/attach_clean_detached_submodule.py \
    tests/agent_tools/test_attach_clean_detached_submodule.py
  bash -n tools/update_agent_canon.sh
  bash tools/agent_tools/scan_dependency_headers.sh \
    --root "${ROOT}" --fail-missing "${changed_paths[@]}"
  bash tools/agent_tools/check_dependency_header_format.sh \
    --root "${ROOT}" --require-header "${changed_paths[@]}"
  tools/bin/agent-canon docs check

  (
    set -euo pipefail
    tmp_root="$(mktemp -d "${TMPDIR:-/tmp}/agent-canon-pr670-parent.XXXXXX")"
    trap 'rm -rf "${tmp_root}"' EXIT
    pr_head="$(git rev-parse HEAD)"
    if git rev-parse --verify HEAD^2 >/dev/null 2>&1; then
      pr_head="$(git rev-parse HEAD^2)"
    fi
    source_merge="$(git rev-parse "${pr_head}^")"
    test "$(git rev-parse "${source_merge}^{tree}")" = "28922fe7550f3c42f40a974df06533369f37f72b"

    agent_remote="${tmp_root}/agent-canon.git"
    seed_parent="${tmp_root}/seed-parent"
    fresh_parent="${tmp_root}/fresh-parent"
    git clone --bare --no-local "${ROOT}" "${agent_remote}" >/dev/null
    git --git-dir="${agent_remote}" update-ref refs/heads/main "${source_merge}"
    git --git-dir="${agent_remote}" symbolic-ref HEAD refs/heads/main

    git clone --no-recurse-submodules \
      https://github.com/iwashita-nozomu/project_template.git \
      "${seed_parent}" >/dev/null
    git -C "${seed_parent}" config user.name "PR 670 Validation"
    git -C "${seed_parent}" config user.email "pr-670-validation@example.invalid"
    git -C "${seed_parent}" config -f .gitmodules \
      submodule.vendor/agent-canon.url "${agent_remote}"
    git -C "${seed_parent}" add .gitmodules
    git -C "${seed_parent}" update-index --add --cacheinfo \
      "160000,${source_merge},vendor/agent-canon"
    git -C "${seed_parent}" commit -m \
      "test: seed exact PR 670 AgentCanon parent pin" >/dev/null

    git -c protocol.file.allow=always clone --recurse-submodules --no-local \
      "${seed_parent}" "${fresh_parent}" >/dev/null
    parent_pin="$(git -C "${fresh_parent}" rev-parse HEAD:vendor/agent-canon)"
    submodule_head="$(git -C "${fresh_parent}/vendor/agent-canon" rev-parse HEAD)"
    submodule_branch="$(git -C "${fresh_parent}/vendor/agent-canon" \
      symbolic-ref --quiet --short HEAD 2>/dev/null || true)"
    submodule_status="$(git -C "${fresh_parent}/vendor/agent-canon" \
      status --porcelain=v1 --untracked-files=all)"
    test "${parent_pin}" = "${source_merge}"
    test "${submodule_head}" = "${parent_pin}"
    test -z "${submodule_branch}"
    test -z "${submodule_status}"

    evidence_digest="$(sha256sum \
      "${fresh_parent}/vendor/agent-canon/agents/workflows/agent-canon-pr-workflow.md" \
      | awk '{print $1}')"
    (
      cd "${fresh_parent}"
      git config user.name "PR 670 Validation"
      git config user.email "pr-670-validation@example.invalid"
      AGENT_CANON_DESTRUCTIVE_GIT_AUTHORITY=explicit_user_approval \
      AGENT_CANON_DESTRUCTIVE_GIT_REASON="PR 670 fresh recurse-submodules parent replay" \
      AGENT_CANON_COMMIT_REQUEST_EVIDENCE="evidence:${evidence_digest}" \
        bash tools/agent-canon/update_agent_canon.sh latest main \
        | tee "${tmp_root}/parent-latest.log"
    )
    grep -q '^AGENT_CANON_DETACHED_ATTACH=attached:main$' \
      "${tmp_root}/parent-latest.log"
    test "$(git -C "${fresh_parent}/vendor/agent-canon" \
      symbolic-ref --quiet --short HEAD)" = main
    test "$(git -C "${fresh_parent}/vendor/agent-canon" rev-parse HEAD)" = \
      "${parent_pin}"
    test -z "$(git -C "${fresh_parent}/vendor/agent-canon" \
      status --porcelain=v1 --untracked-files=all)"
    echo "PR_670_FRESH_RECURSE_PARENT_REPLAY=pass"
  )
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
  run_pr_670_validation
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
