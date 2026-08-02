#!/usr/bin/env bash
# @dependency-start
# contract tool
# responsibility Checks agent canon pr CI readiness.
# upstream design ../../tools/README.md shared automation index
# upstream design ../../agents/workflows/agent-canon-pr-workflow.md shared canon PR workflow
# upstream design ../../documents/design/dependency-manifest-design.md changed-responsibility graph acceptance contract
# upstream design ../../.github/PULL_REQUEST_TEMPLATE.md standalone AgentCanon PR checklist
# upstream design ../../.github/PULL_REQUEST_TEMPLATE/agent_canon.md template AgentCanon PR checklist
# upstream design ../../templates/documents/github/pull-request/agent_canon.md canonical template-side AgentCanon PR checklist
# upstream implementation ../agent_tools/run_repo_dependency_review.sh strict dependency review
# upstream implementation ./agent_canon_pr_graph_selector.py selects and evaluates parent graph gating from trusted diff and persisted graph evidence
# upstream implementation ../agent_tools/evaluate_skill_workflow_prompts.py skill/workflow prompt parity eval
# upstream implementation ../agent_tools/run_accumulated_agent_evals.py writes required eval family reports before accumulation validation
# upstream implementation ../agent_tools/generated_artifact_guard.py rejects regenerated report leftovers before PR check pass
# upstream implementation ../agent_tools/check_agent_runtime_alignment.py Codex runtime role alignment eval
# upstream implementation ../agent_tools/check_convention_compliance.py convention gate wiring eval
# upstream implementation ../agent_tools/skill_tool_commands.py runtime skill command packet gate
# upstream implementation ../agent_tools/update_lifecycle_contract.py owns G1-G3 receipt identity.
# upstream implementation ./check_github_workflows.py GitHub workflow and PR template checks
# upstream implementation ./run_all_checks.sh quick CI implementation
# @dependency-end

set -euo pipefail

if [[ "$#" -ne 0 ]]; then
  echo "usage: $0" >&2
  exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
source "${SCRIPT_DIR}/../lib/repo_paths.sh"
WORKSPACE_ROOT="$(agent_canon_repo_root "${BASH_SOURCE[0]}")"
CANON_TOOLS_ROOT="$(agent_canon_source_tools_root "${WORKSPACE_ROOT}")"
CANON_SYNC_TOOL="${CANON_TOOLS_ROOT}/sync_agent_canon.sh"
if [ ! -f "${CANON_SYNC_TOOL}" ]; then
  CANON_SYNC_TOOL="${CANON_TOOLS_ROOT}/agent-canon/sync_agent_canon.sh"
fi
if [ ! -f "${CANON_SYNC_TOOL}" ]; then
  echo "AGENT_CANON_PR_SOURCE_TOOLS_ROOT=missing"
  echo "AGENT_CANON_PR_SOURCE_TOOLS_REASON=agent_canon_source_tools_root_resolve_failed"
  exit 1
fi
AGENT_CANON_CLI_TARGET_DIR="${AGENT_CANON_CLI_TARGET_DIR:-${HOME}/.tools/agent-canon/cargo-target}"
AGENT_CANON_SOURCE_ROOT="${WORKSPACE_ROOT}"
if [ ! -f "${AGENT_CANON_SOURCE_ROOT}/rust/agent-canon/Cargo.toml" ] \
  && [ -f "${WORKSPACE_ROOT}/vendor/agent-canon/rust/agent-canon/Cargo.toml" ]; then
  AGENT_CANON_SOURCE_ROOT="${WORKSPACE_ROOT}/vendor/agent-canon"
fi
cd "${WORKSPACE_ROOT}"

AGENT_CANON_PR_TEMP_ROOT_CREATED=0
if [[ -z "${AGENT_CANON_PR_TEMP_ROOT:-}" ]]; then
  AGENT_CANON_PR_TEMP_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/agent-canon-pr-check.XXXXXX")"
  AGENT_CANON_PR_TEMP_ROOT_CREATED=1
fi
PR_GATE_RECEIPT="${AGENT_CANON_PR_TEMP_ROOT}/pr-gate-prepared.receipt"
cleanup_agent_canon_pr_temp_root() {
  if [[ -n "${PR_GATE_RECEIPT:-}" ]]; then
    rm -f -- "${PR_GATE_RECEIPT}" 2>/dev/null || true
  fi
  if [[ "${AGENT_CANON_PR_TEMP_ROOT_CREATED}" -eq 1 ]]; then
    rm -rf "${AGENT_CANON_PR_TEMP_ROOT}"
  fi
}
trap cleanup_agent_canon_pr_temp_root EXIT
PR_DEPENDENCY_REVIEW_DIR="${AGENT_CANON_PR_TEMP_ROOT}/dependency-review/agent-canon-pr"
PR_AGENT_EVAL_LOG_DIR="${AGENT_CANON_PR_TEMP_ROOT}/agent-eval-runs/agent-canon-pr-gate"
PR_RUN_ALL_CHECKS_LOG_DIR="${AGENT_CANON_PR_TEMP_ROOT}/agent-eval-runs/run-all-checks"
PR_QUICK_CI_ARGS=(--quick --skip-docs --skip-github-workflows)
AGENT_CANON_G1_BUNDLE_ACTIVE=0
if [[ -d vendor/agent-canon && -f .gitmodules ]]; then
  PR_AGENT_CANON_SOURCE_ROOT="${WORKSPACE_ROOT}/vendor/agent-canon"
else
  PR_AGENT_CANON_SOURCE_ROOT="${WORKSPACE_ROOT}"
fi
PR_HOOK_ARCHIVE_DIR="${AGENT_CANON_HOOK_ARCHIVE_DIR:-${PR_AGENT_CANON_SOURCE_ROOT}/.agent-canon/log-archive}"
mkdir -p "${PR_HOOK_ARCHIVE_DIR}"

REMOTE_NAME="${AGENT_CANON_REMOTE_NAME:-agent-canon}"
AGENT_CANON_GITHUB_REPO="${AGENT_CANON_GITHUB_REPO:-iwashita-nozomu/agent-canon}"
TEMPLATE_GITHUB_REPO="${TEMPLATE_GITHUB_REPO:-iwashita-nozomu/project_template}"
REMOTE_URL="<unset>"
if git remote get-url "${REMOTE_NAME}" >/dev/null 2>&1; then
  REMOTE_URL="$(git remote get-url "${REMOTE_NAME}")"
fi
if [[ -d vendor/agent-canon && -f .gitmodules ]]; then
  AGENT_CANON_REPOSITORY_MODE="template_or_derived"
else
  AGENT_CANON_REPOSITORY_MODE="standalone_source"
fi
run_direct_agent_checks() {
  if [[ "${AGENT_CANON_REPOSITORY_MODE}" == "template_or_derived" ]]; then
    bash "${CANON_SYNC_TOOL}" check
  else
    echo "SHARED_SURFACE_DRIFT=not_applicable_standalone_source"
  fi
  run_convention_compliance_gate
  python3 "${CANON_TOOLS_ROOT}/agent_tools/check_agent_runtime_alignment.py"
  AGENT_CANON_HOOK_ARCHIVE_DIR="${PR_HOOK_ARCHIVE_DIR}" \
    python3 "${CANON_TOOLS_ROOT}/agent_tools/evaluate_codex_agent_roles.py" --accumulate
  AGENT_CANON_HOOK_ARCHIVE_DIR="${PR_HOOK_ARCHIVE_DIR}" \
    python3 "${CANON_TOOLS_ROOT}/agent_tools/evaluate_skill_workflow_prompts.py" --manifest evidence/agent-evals/skill_workflow_prompt_eval.toml --accumulate
}

run_convention_compliance_gate() {
  python3 "${CANON_TOOLS_ROOT}/agent_tools/check_convention_compliance.py" --root "${WORKSPACE_ROOT}" --format json
}

run_shared_surface_status() {
  if [[ "${AGENT_CANON_REPOSITORY_MODE}" == "template_or_derived" ]]; then
    bash "${CANON_SYNC_TOOL}" status
  else
    echo "SHARED_SURFACE_STATUS=not_applicable_standalone_source"
  fi
}

run_shared_surface_check() {
  if [[ "${AGENT_CANON_REPOSITORY_MODE}" == "template_or_derived" ]]; then
    bash "${CANON_SYNC_TOOL}" check
  else
    echo "SHARED_SURFACE_DRIFT=not_applicable_standalone_source"
  fi
}

run_agent_canon() {
  if [ -x "${CANON_TOOLS_ROOT}/bin/agent-canon" ]; then
    "${CANON_TOOLS_ROOT}/bin/agent-canon" "$@"
    return $?
  fi
  if [ -x "${AGENT_CANON_SOURCE_ROOT}/tools/bin/agent-canon" ]; then
    "${AGENT_CANON_SOURCE_ROOT}/tools/bin/agent-canon" "$@"
    return $?
  fi
  if [ -x "${AGENT_CANON_SOURCE_ROOT}/rust/agent-canon/target/debug/agent-canon" ]; then
    "${AGENT_CANON_SOURCE_ROOT}/rust/agent-canon/target/debug/agent-canon" "$@"
    return $?
  fi
  if [ -x "${AGENT_CANON_SOURCE_ROOT}/rust/agent-canon/target/release/agent-canon" ]; then
    "${AGENT_CANON_SOURCE_ROOT}/rust/agent-canon/target/release/agent-canon" "$@"
    return $?
  fi
  if command -v cargo >/dev/null 2>&1 \
    && [ -f "${AGENT_CANON_SOURCE_ROOT}/rust/agent-canon/Cargo.toml" ]; then
    CARGO_TARGET_DIR="${AGENT_CANON_CLI_TARGET_DIR}" \
      cargo run --quiet --manifest-path "${AGENT_CANON_SOURCE_ROOT}/rust/agent-canon/Cargo.toml" -- "$@"
    return $?
  fi
  echo "AGENT_CANON_CLI_BLOCKER=agent_canon_cli_unavailable" >&2
  echo "AGENT_CANON_CLI_REASON=agent-canon CLI binary/shim missing and cargo route unavailable" >&2
  return 127
}

PR_GATE_DEPENDENCY_GRAPH_REASON=""
PR_GATE_DEPENDENCY_GRAPH_EVIDENCE=""
PR_GATE_DEPENDENCY_GRAPH_BASE_SHA=""
agentcanon_pr_dependency_graph_required() {
  local base_fetch_output=""
  local base_fetch_rc=0
  local base_fetch_status=""
  local trusted_base_sha=""
  local selector_output=""
  local selector_rc=0
  local selector_status=""
  local selector_args=(
    --root "${WORKSPACE_ROOT}"
    --source-root "${AGENT_CANON_SOURCE_ROOT}"
  )

  if [[ "${AGENT_CANON_REPOSITORY_MODE}" == "standalone_source" ]]; then
    echo "AGENT_CANON_PR_DEPENDENCY_GRAPH=required reason=standalone_source"
    PR_GATE_DEPENDENCY_GRAPH_REASON="standalone_source"
    PR_GATE_DEPENDENCY_GRAPH_EVIDENCE="source_root=${AGENT_CANON_SOURCE_ROOT}"
    return 0
  fi
  if [[ "${GITHUB_ACTIONS:-}" == "true" ]]; then
    if base_fetch_output="$(python3 "${CANON_TOOLS_ROOT}/ci/agent_canon_pr_graph_selector.py" \
      --root "${WORKSPACE_ROOT}" \
      --source-root "${AGENT_CANON_SOURCE_ROOT}" \
      --prepare-ci-base)"; then
      base_fetch_rc=0
    else
      base_fetch_rc=$?
    fi
    printf '%s\n' "${base_fetch_output}"
    base_fetch_status="$(awk -F= '$1 == "AGENT_CANON_PR_BASE_FETCH" {print $2}' <<<"${base_fetch_output}")"
    trusted_base_sha="$(awk -F= '$1 == "AGENT_CANON_PR_TRUSTED_BASE_SHA" {print $2}' <<<"${base_fetch_output}")"
    if [[ "${base_fetch_rc}:${base_fetch_status}" != "0:pass" || -z "${trusted_base_sha}" ]]; then
      PR_GATE_DEPENDENCY_GRAPH_REASON="$(awk -F= '$1 == "AGENT_CANON_PR_BASE_FETCH_REASON" {sub(/^[^=]*=/, ""); print}' <<<"${base_fetch_output}")"
      PR_GATE_DEPENDENCY_GRAPH_EVIDENCE="$(awk -F= '$1 == "AGENT_CANON_PR_BASE_FETCH_EVIDENCE" {sub(/^[^=]*=/, ""); print}' <<<"${base_fetch_output}")"
      echo "AGENT_CANON_PR_DEPENDENCY_GRAPH=fail"
      echo "AGENT_CANON_PR_DEPENDENCY_GRAPH_REASON=${PR_GATE_DEPENDENCY_GRAPH_REASON:-pr_base_fetch_failed}"
      echo "AGENT_CANON_PR_DEPENDENCY_GRAPH_EVIDENCE=${PR_GATE_DEPENDENCY_GRAPH_EVIDENCE:-base_fetch_status_missing}"
      echo "AGENT_CANON_PR_DEPENDENCY_GRAPH_SELECTOR=fail rc=${base_fetch_rc} status=${base_fetch_status:-missing}" >&2
      return 2
    fi
    selector_args+=(--trusted-base-sha "${trusted_base_sha}")
  fi
  if selector_output="$(python3 "${CANON_TOOLS_ROOT}/ci/agent_canon_pr_graph_selector.py" \
    "${selector_args[@]}")"; then
    selector_rc=0
  else
    selector_rc=$?
  fi
  printf '%s\n' "${selector_output}"
  selector_status="$(awk -F= '$1 == "AGENT_CANON_PR_DEPENDENCY_GRAPH" {print $2}' <<<"${selector_output}")"
  PR_GATE_DEPENDENCY_GRAPH_REASON="$(awk -F= '$1 == "AGENT_CANON_PR_DEPENDENCY_GRAPH_REASON" {sub(/^[^=]*=/, ""); print}' <<<"${selector_output}")"
  PR_GATE_DEPENDENCY_GRAPH_EVIDENCE="$(awk -F= '$1 == "AGENT_CANON_PR_DEPENDENCY_GRAPH_EVIDENCE" {sub(/^[^=]*=/, ""); print}' <<<"${selector_output}")"
  PR_GATE_DEPENDENCY_GRAPH_BASE_SHA="$(awk -v RS=';' -F= '$1 == "base" {print $2}' <<<"${PR_GATE_DEPENDENCY_GRAPH_EVIDENCE}")"
  case "${selector_rc}:${selector_status}" in
    0:required)
      if [[ ! "${PR_GATE_DEPENDENCY_GRAPH_BASE_SHA}" =~ ^[0-9a-fA-F]{40}$ ]]; then
        echo "AGENT_CANON_PR_DEPENDENCY_GRAPH_SELECTOR=fail reason=selected_base_missing" >&2
        return 2
      fi
      return 0
      ;;
    10:skipped) return 1 ;;
    *)
      echo "AGENT_CANON_PR_DEPENDENCY_GRAPH_SELECTOR=fail rc=${selector_rc} status=${selector_status:-missing}" >&2
      return 2
      ;;
  esac
}

agentcanon_pr_branch_dirty() {
  local submodule_dirty=""
  if [[ "${AGENT_CANON_REPOSITORY_MODE}" != "template_or_derived" ]]; then
    return 1
  fi
  submodule_dirty="$(git -C vendor/agent-canon status --short --untracked-files=all 2>/dev/null || true)"
  [[ -n "${submodule_dirty}" ]]
}

agentcanon_pr_branch_pending() {
  local submodule_head=""
  local parent_pin=""
  local remote_main=""
  if [[ "${AGENT_CANON_REPOSITORY_MODE}" != "template_or_derived" ]]; then
    return 1
  fi
  if agentcanon_pr_branch_dirty; then
    return 1
  fi
  submodule_head="$(git -C vendor/agent-canon rev-parse HEAD 2>/dev/null || true)"
  parent_pin="$(git rev-parse HEAD:vendor/agent-canon 2>/dev/null || true)"
  if [[ -z "${submodule_head}" || -z "${parent_pin}" ]]; then
    return 1
  fi
  if [[ "${submodule_head}" != "${parent_pin}" ]]; then
    return 1
  fi

  remote_main="$(git ls-remote --exit-code "${REMOTE_URL}" refs/heads/main 2>/dev/null | awk '{print $1}')"
  if [[ -z "${remote_main}" ]]; then
    return 1
  fi
  [[ "${parent_pin}" != "${remote_main}" ]]
}

agentcanon_pr_submodule_remote_reachable() {
  local remote_url="$1"
  local pin_ref="$2"
  if [[ -z "${remote_url}" || -z "${pin_ref}" ]]; then
    return 1
  fi
  if ! git -C vendor/agent-canon cat-file -e "${pin_ref}^{commit}" >/dev/null 2>&1; then
    git -C vendor/agent-canon fetch --no-write-fetch-head "${remote_url}" "${pin_ref}" >/dev/null 2>&1 || return 1
  fi
  git -C vendor/agent-canon cat-file -e "${pin_ref}^{commit}" >/dev/null 2>&1
}

agentcanon_pr_branch_integrity() {
  local submodule_head=""
  local parent_pin=""
  local remote_url="${REMOTE_URL}"
  if [[ "${AGENT_CANON_REPOSITORY_MODE}" != "template_or_derived" ]]; then
    return 0
  fi
  submodule_head="$(git -C vendor/agent-canon rev-parse HEAD 2>/dev/null || true)"
  parent_pin="$(git rev-parse HEAD:vendor/agent-canon 2>/dev/null || true)"
  if [[ -z "${submodule_head}" || -z "${parent_pin}" ]]; then
    echo "AGENT_CANON_PR_LATEST_GATE=blocked_agentcanon_submodule_state"
    echo "AGENT_CANON_PR_LATEST_NEXT=repair_submodule_state_and_rerun_agent-canon-pr-check"
    return 3
  fi
  if [[ "${submodule_head}" != "${parent_pin}" ]]; then
    echo "AGENT_CANON_PR_LATEST_GATE=blocked_submodule_gitlink_mismatch"
    echo "AGENT_CANON_PR_LATEST_REASON=submodule-gitlink-worktree-mismatch"
    echo "AGENT_CANON_PR_LATEST_NEXT=run_make_agent-canon-ensure-latest_then_commit_updated_submodule_pin_with_request_evidence"
    return 4
  fi
  if ! agentcanon_pr_submodule_remote_reachable "${remote_url}" "${parent_pin}"; then
    echo "AGENT_CANON_PR_LATEST_GATE=blocked_submodule_pin_unreachable"
    echo "AGENT_CANON_PR_LATEST_REASON=submodule-pinned-commit-unreachable-from-configured-remote"
    echo "AGENT_CANON_PR_LATEST_NEXT=run_agent_canon_update_or_update_agent-canon-remote_reference"
    return 5
  fi
  return 0
}

agentcanon_pr_update_precondition() {
  local submodule_head=""
  local parent_pin=""
  local remote_url="${REMOTE_URL}"
  if [[ "${AGENT_CANON_REPOSITORY_MODE}" != "template_or_derived" ]]; then
    return 0
  fi
  if [[ -n "${REMOTE_URL:-}" && -n "${REMOTE_URL#<unset>}" ]] && agentcanon_pr_branch_dirty; then
    echo "AGENT_CANON_PR_UPDATE_STATE=dirty_agentcanon_worktree_preserved"
    echo "AGENT_CANON_PR_UPDATE_NEXT=run_make_agent-canon-ensure-latest_with_dirty_worktree_preserved"
  fi
  submodule_head="$(git -C vendor/agent-canon rev-parse HEAD 2>/dev/null || true)"
  parent_pin="$(git rev-parse HEAD:vendor/agent-canon 2>/dev/null || true)"
  if [[ -z "${submodule_head}" || -z "${parent_pin}" ]]; then
    echo "AGENT_CANON_PR_UPDATE_GATE=blocked_agentcanon_submodule_state"
    echo "AGENT_CANON_PR_UPDATE_NEXT=repair_submodule_state_and_rerun_agent-canon-pr-check"
    return 3
  fi
  if [[ "${submodule_head}" != "${parent_pin}" ]]; then
    echo "AGENT_CANON_PR_UPDATE_GATE=blocked_submodule_gitlink_mismatch"
    echo "AGENT_CANON_PR_UPDATE_REASON=submodule-gitlink-worktree-mismatch"
    echo "AGENT_CANON_PR_UPDATE_NEXT=run_make_agent-canon-ensure-latest_then_commit_updated_submodule_pin_with_request_evidence"
    return 4
  fi
  if ! agentcanon_pr_submodule_remote_reachable "${remote_url}" "${parent_pin}"; then
    echo "AGENT_CANON_PR_UPDATE_GATE=blocked_submodule_pin_unreachable"
    echo "AGENT_CANON_PR_UPDATE_REASON=submodule-pinned-commit-unreachable-from-configured-remote"
    echo "AGENT_CANON_PR_UPDATE_NEXT=run_agent_canon_update_or_update_agent-canon-remote_reference"
    return 5
  fi
  return 0
}

run_pr_integrity_check() {
  local rc=0
  set +e
  agentcanon_pr_branch_integrity
  rc=$?
  set -e
  return $rc
}

run_pr_agent_checks() {
  if [[ "${AGENT_CANON_REPOSITORY_MODE}" == "standalone_source" ]]; then
    run_standalone_static_gate_ci
    return
  fi
  local integrity_rc=0
  run_pr_integrity_check
  integrity_rc=$?
  if [[ "$integrity_rc" -ne 0 ]]; then
    echo "AGENT_CANON_PR_LATEST_GATE=${AGENT_CANON_PR_LATEST_GATE:-blocked_submodule_integrity}"
    echo "AGENT_CANON_PR_LATEST_NEXT=${AGENT_CANON_PR_LATEST_NEXT:-repair_submodule_state_and_rerun_agent-canon-pr-check}"
    return 1
  fi
  if agentcanon_pr_branch_dirty; then
    echo "AGENT_CANON_PR_LATEST_DIRTY_AGENTCANON_WORKTREE=yes"
    echo "AGENT_CANON_PR_LATEST_NEXT=run_make_agent-canon-ensure-latest_with_dirty_worktree_preserved"
  fi
  if agentcanon_pr_branch_pending; then
    echo "AGENT_CANON_PR_LATEST_GATE=deferred_branch_pr"
    echo "AGENT_CANON_PR_LATEST_NEXT=commit_push_agentcanon_branch_then_after_merge_run_make_agent-canon-ensure-latest"
    run_direct_agent_checks
    return
  fi
  if [[ -f Makefile ]] && grep -qE "^[.]?PHONY:.*\\bagent-checks\\b|^agent-checks:" Makefile; then
    make agent-checks
  else
    bash "${CANON_TOOLS_ROOT}/ci/check_agent_canon_latest.sh"
    run_direct_agent_checks
  fi
}

run_pr_quick_ci() {
  if [[ "${AGENT_CANON_REPOSITORY_MODE}" == "standalone_source" ]]; then
    echo "AGENT_CANON_PR_QUICK_CI=consumed_standalone_static_gate_receipt"
    return
  fi
  local integrity_rc=0
  local quick_ci_rc=0
  local latest_ci_gate="pass"
  local latest_ci_next="run_all_checks"
  AGENT_CANON_PR_LATEST_GATE=""
  AGENT_CANON_PR_LATEST_NEXT=""
  run_pr_integrity_check
  integrity_rc=$?
  if [[ "$integrity_rc" -ne 0 ]]; then
    echo "AGENT_CANON_PR_CI_LATEST_GATE=${AGENT_CANON_PR_LATEST_GATE:-blocked_submodule_integrity}"
    echo "AGENT_CANON_PR_CI_LATEST_NEXT=${AGENT_CANON_PR_LATEST_NEXT:-repair_submodule_integrity_and_rerun_agent-canon-pr-check}"
    return 1
  fi
  if agentcanon_pr_branch_pending; then
    latest_ci_gate="deferred_branch_pr"
    latest_ci_next="run_all_checks_or_merge_agent-canon-PR"
    echo "AGENT_CANON_PR_CI_COMMAND=bash ${CANON_TOOLS_ROOT}/ci/run_all_checks.sh ${PR_QUICK_CI_ARGS[*]} --pr-gate-receipt ${PR_GATE_RECEIPT}"
    set +e
    AGENT_CANON_CI_EVAL_LOG_DIR="${PR_RUN_ALL_CHECKS_LOG_DIR}" \
      bash "${CANON_TOOLS_ROOT}/ci/run_all_checks.sh" "${PR_QUICK_CI_ARGS[@]}" --pr-gate-receipt "${PR_GATE_RECEIPT}"
    quick_ci_rc=$?
    set -e
    echo "AGENT_CANON_PR_CI_LATEST_GATE=${latest_ci_gate}"
    echo "AGENT_CANON_PR_CI_LATEST_NEXT=${latest_ci_next}"
    echo "AGENT_CANON_PR_CI_EXIT=${quick_ci_rc}"
    return "$quick_ci_rc"
  fi
  echo "AGENT_CANON_PR_CI_COMMAND=bash ${CANON_TOOLS_ROOT}/ci/run_all_checks.sh ${PR_QUICK_CI_ARGS[*]} --pr-gate-receipt ${PR_GATE_RECEIPT}"
  set +e
  AGENT_CANON_CI_EVAL_LOG_DIR="${PR_RUN_ALL_CHECKS_LOG_DIR}" \
    bash "${CANON_TOOLS_ROOT}/ci/run_all_checks.sh" "${PR_QUICK_CI_ARGS[@]}" --pr-gate-receipt "${PR_GATE_RECEIPT}"
  quick_ci_rc=$?
  set -e
  echo "AGENT_CANON_PR_CI_LATEST_GATE=${latest_ci_gate}"
  echo "AGENT_CANON_PR_CI_LATEST_NEXT=${latest_ci_next}"
  echo "AGENT_CANON_PR_CI_EXIT=${quick_ci_rc}"
  return "$quick_ci_rc"
}

write_pr_gate_receipt() {
  local root_identity=""
  local dependency_graph_status="${1:-}"
  local selector_reason="${2:-}"
  local selector_evidence="${3:-}"
  if ! root_identity="$(realpath -e "${WORKSPACE_ROOT}")"; then
    echo "Unable to record PR gate root identity" >&2
    return 1
  fi
  case "${dependency_graph_status}" in
    prepared|scoped|skipped) ;;
    *)
      echo "Invalid PR gate dependency graph status: ${dependency_graph_status}" >&2
      return 1
      ;;
  esac
  if [[ -z "${selector_reason}" || -z "${selector_evidence}" \
    || "${selector_reason}" == *$'\n'* || "${selector_evidence}" == *$'\n'* ]]; then
    echo "Invalid PR gate dependency graph selector reason/evidence" >&2
    return 1
  fi
  {
    printf 'owner=check_agent_canon_pr.sh\n'
    printf 'root_identity=%s\n' "${root_identity}"
    printf 'parent_pid=%s\n' "$$"
    printf 'strict_dependency=%s\n' "${dependency_graph_status}"
    printf 'graph=%s\n' "${dependency_graph_status}"
    printf 'selector_reason=%s\n' "${selector_reason}"
    printf 'selector_evidence=%s\n' "${selector_evidence}"
  } >"${PR_GATE_RECEIPT}"
}

consume_source_correctness_receipt() {
  local bundle="${AGENT_CANON_PR_GATE_BUNDLE:-}"
  if [[ -z "${bundle}" ]]; then
    echo "AGENT_CANON_G1_RECEIPT=not_materialized_nontransaction"
    return
  fi
  PYTHONPATH="${PR_AGENT_CANON_SOURCE_ROOT}/tools/agent_tools${PYTHONPATH:+:${PYTHONPATH}}" \
    python3 - "${bundle}" <<'PY'
import json
import sys
from pathlib import Path
from update_lifecycle_contract import validate_gate_chain

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
values = payload.get("gate_verdicts") if isinstance(payload, dict) else None
if not isinstance(values, list):
    raise SystemExit("agent_canon_pr_gate_bundle:gate_verdicts_missing")
validate_gate_chain(values, expected_gate_ids=("G1",), require_pass=True)
print("AGENT_CANON_G1_RECEIPT=consumed")
print("AGENT_CANON_PR_GATE_ORDER=G1")
PY
  AGENT_CANON_G1_BUNDLE_ACTIVE=1
}

emit_generated_completeness_receipt() {
  local bundle="${AGENT_CANON_PR_GATE_BUNDLE:-}"
  local output="${AGENT_CANON_G2_OUTPUT:-}"
  local command=(
    python3 "${PR_AGENT_CANON_SOURCE_ROOT}/tools/ci/check_agent_canon_pr.py"
    --g1-bundle "${bundle}"
    --source-root "${PR_AGENT_CANON_SOURCE_ROOT}"
  )
  if [[ "${AGENT_CANON_G1_BUNDLE_ACTIVE}" -ne 1 ]]; then
    echo "AGENT_CANON_G2_RECEIPT=not_materialized_nontransaction"
    return
  fi
  if [[ -n "${output}" ]]; then
    command+=(--output "${output}")
  fi
  "${command[@]}"
}

run_standalone_static_gate_ci() {
  cargo fmt --manifest-path rust/agent-canon/Cargo.toml -- --check
  cargo clippy --manifest-path rust/agent-canon/Cargo.toml --all-targets -- -D warnings
  cargo test --manifest-path rust/agent-canon/Cargo.toml
  python3 "${CANON_TOOLS_ROOT}/agent_tools/tool_catalog.py"
  python3 "${CANON_TOOLS_ROOT}/agent_tools/tool_proof_coverage.py"
  python3 "${CANON_TOOLS_ROOT}/agent_tools/responsibility_scope.py"
  BASE_REF="${GITHUB_BASE_REF:-main}"
  git fetch origin "${BASE_REF}" --depth=1 || true
  python3 "${CANON_TOOLS_ROOT}/agent_tools/import_responsibility.py" --changed --baseline-ref "origin/${BASE_REF}"
  python3 "${CANON_TOOLS_ROOT}/agent_tools/issue_sync.py"
  AGENT_CANON_HOOK_ARCHIVE_DIR="${PR_HOOK_ARCHIVE_DIR}" \
    python3 "${CANON_TOOLS_ROOT}/agent_tools/run_accumulated_agent_evals.py" --run-id agent-canon-pr-gate --log-dir "${PR_AGENT_EVAL_LOG_DIR}"
  AGENT_CANON_HOOK_ARCHIVE_DIR="${PR_HOOK_ARCHIVE_DIR}" \
    python3 "${CANON_TOOLS_ROOT}/agent_tools/eval_accumulation_check.py"
  python3 "${CANON_TOOLS_ROOT}/agent_tools/check_agent_runtime_alignment.py"
  python3 "${CANON_TOOLS_ROOT}/agent_tools/smoke_test_research_perspective_pack.py"
  run_convention_compliance_gate
  python3 "${CANON_TOOLS_ROOT}/agent_tools/skill_tool_commands.py" check
  python3 "${CANON_TOOLS_ROOT}/ci/check_github_workflows.py"
  python3 "${CANON_TOOLS_ROOT}/ci/container_config.py"
}

github_repo_security_status() {
  local repo="$1"
  local label="$2"
  local repo_json=""
  local remote_sha=""
  echo "${label}_repo=${repo}"
  if ! command -v gh >/dev/null 2>&1; then
    echo "${label}_gh=unavailable"
    return
  fi
  if repo_json="$(gh repo view "${repo}" --json nameWithOwner,visibility,isPrivate,defaultBranchRef 2>/dev/null)"; then
    echo "${label}_gh=visible"
    echo "${label}_metadata=${repo_json}"
  else
    echo "${label}_gh=not_visible_or_not_created"
    return
  fi
  if remote_sha="$(git ls-remote "https://github.com/${repo}.git" main 2>/dev/null | awk '{print $1}')"; then
    echo "${label}_github_main_sha=${remote_sha:-<missing>}"
  else
    echo "${label}_github_main_sha=<unavailable>"
  fi
  if gh api "repos/${repo}/branches/main/protection" >/dev/null 2>&1; then
    echo "${label}_branch_protection=enabled"
  else
    echo "${label}_branch_protection=missing_or_unavailable"
  fi
  if gh api "repos/${repo}/vulnerability-alerts" >/dev/null 2>&1; then
    echo "${label}_vulnerability_alerts=enabled"
  else
    echo "${label}_vulnerability_alerts=disabled_or_unavailable"
  fi
  if gh api "repos/${repo}/dependabot/alerts" --jq length >/dev/null 2>&1; then
    echo "${label}_dependabot_alerts=readable"
  else
    echo "${label}_dependabot_alerts=disabled_or_scope_missing"
  fi
}

echo "=========================================="
echo "AGENT-CANON PR CHECK"
echo "=========================================="
echo "workspace_root=${WORKSPACE_ROOT}"
echo "agent_canon_pr_temp_root=${AGENT_CANON_PR_TEMP_ROOT}"
echo "agent_canon_repository_mode=${AGENT_CANON_REPOSITORY_MODE}"
echo "agent_canon_remote=${REMOTE_URL}"
consume_source_correctness_receipt
if [[ "${AGENT_CANON_REPOSITORY_MODE}" == "template_or_derived" ]]; then
  echo "agent_canon_submodule_status=$(git submodule status vendor/agent-canon 2>/dev/null || true)"
  agent_canon_gitmodules_url="$(git config -f .gitmodules --get submodule.vendor/agent-canon.url 2>/dev/null || true)"
  agent_canon_submodule_mode="$(git ls-tree HEAD vendor/agent-canon 2>/dev/null | awk '{print $1}')"
  agent_canon_submodule_pin="$(git rev-parse HEAD:vendor/agent-canon 2>/dev/null || true)"
  echo "agent_canon_gitmodules_url=${agent_canon_gitmodules_url:-<missing>}"
  echo "agent_canon_submodule_mode=${agent_canon_submodule_mode:-<missing>}"
  echo "agent_canon_submodule_pin=${agent_canon_submodule_pin:-<missing>}"
  if [[ -z "$agent_canon_gitmodules_url" || "$agent_canon_submodule_mode" != "160000" || -z "$agent_canon_submodule_pin" ]]; then
    echo "AGENT_CANON_SUBMODULE_EVIDENCE=fail"
    exit 1
  fi
  echo "AGENT_CANON_SUBMODULE_EVIDENCE=pass"
else
  echo "agent_canon_submodule_status=<not_applicable>"
  echo "agent_canon_gitmodules_url=<not_applicable>"
  echo "agent_canon_submodule_mode=<not_applicable>"
  echo "agent_canon_submodule_pin=<not_applicable>"
  echo "AGENT_CANON_SUBMODULE_EVIDENCE=not_applicable_standalone_source"
fi
echo ""

echo "1️⃣  shared surface status"
run_shared_surface_status
echo ""

echo "2️⃣  shared surface drift check"
run_shared_surface_check
echo ""

echo "2b️⃣  GitHub workflow and PR template checks"
if [[ "${AGENT_CANON_REPOSITORY_MODE}" == "template_or_derived" ]]; then
  python3 "${CANON_TOOLS_ROOT}/ci/check_github_workflows.py"
else
  echo "GITHUB_WORKFLOW_CHECK=owned_by_standalone_static_gate"
fi
echo ""

echo "3️⃣  changed shared canon paths"
git status --short -- vendor/agent-canon .github/workflows/agent-coordination.yml .github/PULL_REQUEST_TEMPLATE/agent_canon.md || true
echo ""

echo "4️⃣  GitHub mirror and security evidence"
github_repo_security_status "${AGENT_CANON_GITHUB_REPO}" "agent_canon_github"
github_repo_security_status "${TEMPLATE_GITHUB_REPO}" "template_github"
echo ""

echo "5️⃣  agent runtime checks"
run_pr_agent_checks
echo ""

echo "6️⃣  dependency graph completeness"
PR_GATE_DEPENDENCY_GRAPH_STATUS=skipped
PR_GATE_DEPENDENCY_GRAPH_SELECTOR_RC=0
if agentcanon_pr_dependency_graph_required; then
  # This graph build produces either a full strict review or scoped diagnostic
  # evidence for the subsequent quick CI receipt consumer.
  mkdir -p "${PR_DEPENDENCY_REVIEW_DIR}"
  graph_build_result="${PR_DEPENDENCY_REVIEW_DIR}/graph-build.json"
  if run_agent_canon graph build --root . --profile default --format json >"${graph_build_result}"; then
    graph_build_rc=0
  else
    graph_build_rc=$?
  fi
  cat "${graph_build_result}"
  if [[ "${graph_build_rc}" -eq 0 ]]; then
    if [[ "${AGENT_CANON_REPOSITORY_MODE}" == "standalone_source" ]]; then
      python3 "${CANON_TOOLS_ROOT}/agent_tools/tool_drift.py"
    fi
    bash "${CANON_TOOLS_ROOT}/agent_tools/run_repo_dependency_review.sh" --fail-missing --cycle-report-only --report-dir "${PR_DEPENDENCY_REVIEW_DIR}"
    python3 "${CANON_TOOLS_ROOT}/agent_tools/render_dependency_manifest_graph.py" \
      --root . \
      --scope full \
      --markdown-out "${PR_DEPENDENCY_REVIEW_DIR}/dependency_manifest_graph.md" \
      --dot-out "${PR_DEPENDENCY_REVIEW_DIR}/dependency_manifest_graph.dot"
    PR_GATE_DEPENDENCY_GRAPH_STATUS=prepared
  elif [[ "${graph_build_rc}" -eq 1 && "${AGENT_CANON_REPOSITORY_MODE}" == "template_or_derived" ]]; then
    graph_acceptance_output=""
    graph_acceptance_rc=0
    graph_acceptance_args=(
      --root "${WORKSPACE_ROOT}"
      --source-root "${AGENT_CANON_SOURCE_ROOT}"
      --evaluate-built-graph
      --graph-result "${graph_build_result}"
      --report-out "${PR_DEPENDENCY_REVIEW_DIR}/changed-responsibility-acceptance.json"
    )
    if [[ "${GITHUB_ACTIONS:-}" == "true" ]]; then
      graph_acceptance_args+=(--trusted-base-sha "${PR_GATE_DEPENDENCY_GRAPH_BASE_SHA}")
    fi
    if graph_acceptance_output="$(python3 "${CANON_TOOLS_ROOT}/ci/agent_canon_pr_graph_selector.py" \
      "${graph_acceptance_args[@]}")"; then
      graph_acceptance_rc=0
    else
      graph_acceptance_rc=$?
    fi
    printf '%s\n' "${graph_acceptance_output}"
    graph_acceptance_status="$(awk -F= '$1 == "AGENT_CANON_PR_GRAPH_ACCEPTANCE" {print $2}' <<<"${graph_acceptance_output}")"
    graph_acceptance_reason="$(awk -F= '$1 == "AGENT_CANON_PR_GRAPH_ACCEPTANCE_REASON" {sub(/^[^=]*=/, ""); print}' <<<"${graph_acceptance_output}")"
    graph_acceptance_evidence="$(awk -F= '$1 == "AGENT_CANON_PR_GRAPH_ACCEPTANCE_EVIDENCE" {sub(/^[^=]*=/, ""); print}' <<<"${graph_acceptance_output}")"
    if [[ -f "${PR_DEPENDENCY_REVIEW_DIR}/changed-responsibility-acceptance.json" ]]; then
      cat "${PR_DEPENDENCY_REVIEW_DIR}/changed-responsibility-acceptance.json"
    fi
    if [[ "${graph_acceptance_rc}:${graph_acceptance_status}" != "0:pass" ]]; then
      echo "AGENT_CANON_PR_DEPENDENCY_GRAPH_GATE=changed_responsibility_failed"
      if [[ "${graph_acceptance_rc}" -eq 0 ]]; then
        exit 2
      fi
      exit "${graph_acceptance_rc}"
    fi
    PR_GATE_DEPENDENCY_GRAPH_EVIDENCE="${PR_GATE_DEPENDENCY_GRAPH_EVIDENCE};graph_acceptance_reason=${graph_acceptance_reason};${graph_acceptance_evidence}"
    PR_GATE_DEPENDENCY_GRAPH_STATUS=scoped
  else
    echo "AGENT_CANON_PR_DEPENDENCY_GRAPH_GATE=graph_build_failed rc=${graph_build_rc}"
    exit "${graph_build_rc}"
  fi
else
  PR_GATE_DEPENDENCY_GRAPH_SELECTOR_RC=$?
  if [[ "${PR_GATE_DEPENDENCY_GRAPH_SELECTOR_RC}" -ne 1 ]]; then
    echo "AGENT_CANON_PR_DEPENDENCY_GRAPH_GATE=selector_failed"
    exit "${PR_GATE_DEPENDENCY_GRAPH_SELECTOR_RC}"
  fi
  echo "AGENT_CANON_PR_DEPENDENCY_GRAPH_GATE=not_required"
fi
write_pr_gate_receipt \
  "${PR_GATE_DEPENDENCY_GRAPH_STATUS}" \
  "${PR_GATE_DEPENDENCY_GRAPH_REASON}" \
  "${PR_GATE_DEPENDENCY_GRAPH_EVIDENCE}"
echo ""

echo "7️⃣  documentation checks"
	run_agent_canon docs check
echo ""

echo "8️⃣  repository quick CI"
run_pr_quick_ci
echo ""

echo "8b️⃣  generated artifact guard"
	python3 "${CANON_TOOLS_ROOT}/agent_tools/generated_artifact_guard.py" --root "${WORKSPACE_ROOT}"
echo ""

emit_generated_completeness_receipt
echo ""

echo "AGENT_CANON_PR_CHECK=pass"
echo "AGENT_CANON_PR_PROPAGATION_WORKFLOW=agents/workflows/agent-canon-pr-workflow.md"
echo "NEXT_ACTION=Open_or_update_AgentCanon_PR_then_after_merge_run_make_agent-canon-ensure-latest_and_commit_template_pin"
