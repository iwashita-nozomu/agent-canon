#!/usr/bin/env bash
# @dependency-start
# contract tool
# responsibility Runs all checks CI automation.
# upstream design ../../documents/design/source-owned-dependency-validation.md source-owned PR receipt contract
# upstream design ../../documents/design/dependency-manifest-design.md manifest DSL and explicit graph analysis projection
# upstream implementation ./check_agent_canon_pr.sh writes owner/root/PID/status-bound source receipts
# upstream implementation ./pr_gate_receipt.py owns receipt parsing and binding validation
# upstream implementation ../agent_tools/parent_root_side_effects.py owns parent-local child state and exact cleanup
# upstream implementation ../agent_tools/check_dependency_headers.py validates changed-file dependency manifests
# upstream implementation ../agent_tools/check_dependency_header_format.sh validates changed-file manifest syntax
# upstream implementation ../agent_tools/check_static_any.py rejects explicit Python Any usage
# upstream implementation ../agent_tools/check_log_helper_names.py validates log helper naming
# upstream implementation ../agent_tools/import_responsibility.py validates import ownership boundaries
# upstream implementation ../validation/notebook_quality.py validates notebooks as readable runnable demos
# upstream implementation ../bin/agent-canon invokes the canonical Rust algorithm contract checker
# upstream implementation ../../rust/agent-canon/src/python_algorithm_contract.rs owns the algorithm contract checker
# upstream implementation ../agent_tools/check_convention_compliance.py validates convention/workflow gate wiring
# upstream implementation ../agent_tools/tool_catalog.py validates structured tool catalog
# upstream implementation ../agent_tools/tool_drift.py validates tool/convention trace contracts
# upstream implementation ../agent_tools/skill_tool_commands.py validates runtime skill command packets
# upstream implementation ../agent_tools/responsibility_scope.py validates responsibility-scope coverage
# upstream implementation ../agent_tools/issue_sync.py validates local issue sync state
# upstream implementation ../agent_tools/run_accumulated_agent_evals.py writes required eval family reports before accumulation validation
# upstream implementation ../agent_tools/eval_accumulation_check.py validates eval result accumulation
# upstream implementation ../agent_tools/runtime_log_archive_git.py manages mounted hook/eval log archive branches
# upstream implementation ../agent_tools/check_skill_frontmatter.py validates runtime skill YAML frontmatter
# upstream implementation ../agent_tools/evaluate_workflow_selection.py validates workflow selection routing cases
# upstream implementation ../agent_tools/evaluate_report_quality.py validates report writing quality checklist cases
# upstream implementation ./check_github_workflows.py validates GitHub workflow and PR checklist contracts
# upstream implementation ./container_config.py validates Dockerfile/devcontainer/runtime pack contracts
# upstream implementation ../agent_tools/smoke_test_research_perspective_pack.py validates research role packet
# @dependency-end
set -euo pipefail

# ═══════════════════════════════════════════════════════════════════════════
# Full confidence CI entrypoint
#
# 用途: agent/runtime, dependency manifest, eval accumulation, Rust,
#       GitHub workflow, container config, documentation, experiment registry,
#       pytest, pyright, and ruff checks を一括実行します。
#       普段の変更では Makefile の check-matrix から対象 profile を選び、
#       この script は full confidence gate として使います。
#
# 使用方法:
#   bash tools/ci/run_all_checks.sh           # full confidence checks
#   bash tools/ci/run_all_checks.sh --quick   # broad checks with ruff skipped
#   bash tools/ci/run_all_checks.sh --quick --skip-docs --skip-github-workflows
#                                               # PR gate reuse after those gates already ran
#   bash tools/ci/run_all_checks.sh --skip-experiments
#                                               # skip the optional experiment registry gate
#
# 前提条件:
#   - Docker 環境、または requirements.txt のパッケージ導入済み
#   - PYTHONPATH は自動設定
#
# 出力:
#   - コンソール: テスト結果・エラー詳細
#   - logs/ci_*.txt: 実行ログ（未実装版はコンソール出力のみ）
#
# 戻り値:
#   - 0: すべてのチェック成功
#   - 1: テスト失敗 または解析エラー
#
# 関連ドキュメント:
#   - documents/tools/README.md: repo-wide tool entrypoints
#   - documents/conventions/REVIEW_PROCESS.md: review と validation の正本
#   - .github/workflows/ci.yml: GitHub Actions ワークフロー
#
# ═══════════════════════════════════════════════════════════════════════════

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
source "${SCRIPT_DIR}/../lib/repo_paths.sh"
WORKSPACE_ROOT="$(agent_canon_repo_root "${BASH_SOURCE[0]}")"
CANON_TOOLS_ROOT="$(agent_canon_source_tools_root "$WORKSPACE_ROOT")"
CANON_CI_ROOT="${CANON_TOOLS_ROOT}/ci"
cd "$WORKSPACE_ROOT"

if [[ -d "${WORKSPACE_ROOT}/vendor/agent-canon" && -f "${WORKSPACE_ROOT}/.gitmodules" ]]; then
  AGENT_CANON_REPOSITORY_MODE="template_or_derived"
  AGENT_CANON_SOURCE_ROOT="${WORKSPACE_ROOT}/vendor/agent-canon"
else
  AGENT_CANON_REPOSITORY_MODE="standalone_source"
  AGENT_CANON_SOURCE_ROOT="$WORKSPACE_ROOT"
fi
AGENT_CANON_CARGO_MANIFEST="${AGENT_CANON_SOURCE_ROOT}/rust/agent-canon/Cargo.toml"
AGENT_CANON_CLI_TARGET_DIR="${AGENT_CANON_CLI_TARGET_DIR:-${WORKSPACE_ROOT}/.agent-canon/cache/cargo-target}"
AGENT_CANON_BOUNDARY_SCRIPT="${CANON_TOOLS_ROOT}/agent_tools/parent_root_side_effects.py"
if [[ -z "${AGENT_CANON_SIDE_EFFECT_HANDOFF:-}" ]]; then
  invocation_script="$(realpath -e "${BASH_SOURCE[0]}" 2>/dev/null || true)"
  if [[ -z "${invocation_script}" || ! -f "${invocation_script}" ]]; then
    echo "RUN_ALL_CHECKS=fail reason=invocation_script_missing" >&2
    exit 2
  fi
  exec python3 "${AGENT_CANON_BOUNDARY_SCRIPT}" public-exec \
    --invocation-script "${invocation_script}" \
    --purpose run-all-checks-script \
    -- bash "${invocation_script}" "$@"
fi

AGENT_CANON_CI_EVAL_LOG_TEMP_CREATED=0
AGENT_CANON_CI_HOOK_ARCHIVE_CREATED=0
AGENT_CANON_CI_EXPLICIT_EVAL_CREATED=0
AGENT_CANON_CI_SETUP_COMPLETE=0
AGENT_CANON_CI_EVAL_LOG_DIR_VALUE=""
AGENT_CANON_CI_HOOK_ARCHIVE_DIR="$(
  python3 "${AGENT_CANON_BOUNDARY_SCRIPT}" resolve \
    --root "${WORKSPACE_ROOT}" \
    --candidate "${AGENT_CANON_HOOK_ARCHIVE_DIR:-${AGENT_CANON_SOURCE_ROOT}/.agent-canon/log-archive}" \
    --purpose run-all-checks-hook-archive
)"
if [[ ! -d "${AGENT_CANON_CI_HOOK_ARCHIVE_DIR}" ]]; then
  AGENT_CANON_CI_HOOK_ARCHIVE_CREATED=1
fi
if [ -n "${AGENT_CANON_CI_EVAL_LOG_DIR:-}" ]; then
  AGENT_CANON_CI_EVAL_LOG_DIR_VALUE="$(
    python3 "${AGENT_CANON_BOUNDARY_SCRIPT}" resolve \
      --root "${WORKSPACE_ROOT}" \
      --candidate "${AGENT_CANON_CI_EVAL_LOG_DIR}" \
      --purpose run-all-checks-explicit-eval-log
  )"
  if [[ ! -d "${AGENT_CANON_CI_EVAL_LOG_DIR_VALUE}" ]]; then
    AGENT_CANON_CI_EXPLICIT_EVAL_CREATED=1
  fi
fi

cleanup_run_all_checks_temp() {
  local status=$?
  local cleanup_status=0
  trap - EXIT
  if [[ "${AGENT_CANON_CI_EVAL_LOG_TEMP_CREATED}" -eq 1 ]]; then
    python3 "${AGENT_CANON_BOUNDARY_SCRIPT}" remove-tree \
      --root "${WORKSPACE_ROOT}" \
      --candidate "${AGENT_CANON_CI_EVAL_LOG_DIR_VALUE}" \
      --purpose run-all-checks-cleanup >/dev/null || cleanup_status=$?
  fi
  if [[ "${AGENT_CANON_CI_SETUP_COMPLETE}" -eq 0 ]]; then
    if [[ "${AGENT_CANON_CI_EXPLICIT_EVAL_CREATED}" -eq 1 ]]; then
      python3 "${AGENT_CANON_BOUNDARY_SCRIPT}" remove-empty-dir \
        --root "${WORKSPACE_ROOT}" \
        --candidate "${AGENT_CANON_CI_EVAL_LOG_DIR_VALUE}" \
        --purpose run-all-checks-setup-rollback >/dev/null || cleanup_status=$?
    fi
    if [[ "${AGENT_CANON_CI_HOOK_ARCHIVE_CREATED}" -eq 1 ]]; then
      python3 "${AGENT_CANON_BOUNDARY_SCRIPT}" remove-empty-dir \
        --root "${WORKSPACE_ROOT}" \
        --candidate "${AGENT_CANON_CI_HOOK_ARCHIVE_DIR}" \
        --purpose run-all-checks-setup-rollback >/dev/null || cleanup_status=$?
    fi
  fi
  if [[ "$status" -eq 0 && "$cleanup_status" -ne 0 ]]; then
    status=$cleanup_status
  fi
  exit "$status"
}
trap cleanup_run_all_checks_temp EXIT

AGENT_CANON_CI_HOOK_ARCHIVE_DIR="$(
  python3 "${AGENT_CANON_BOUNDARY_SCRIPT}" ensure-dir \
    --root "${WORKSPACE_ROOT}" \
    --candidate "${AGENT_CANON_CI_HOOK_ARCHIVE_DIR}" \
    --purpose run-all-checks-hook-archive
)"
if [ -n "${AGENT_CANON_CI_EVAL_LOG_DIR:-}" ]; then
  AGENT_CANON_CI_EVAL_LOG_DIR_VALUE="$(
    python3 "${AGENT_CANON_BOUNDARY_SCRIPT}" ensure-dir \
      --root "${WORKSPACE_ROOT}" \
      --candidate "${AGENT_CANON_CI_EVAL_LOG_DIR_VALUE}" \
      --purpose run-all-checks-explicit-eval-log
  )"
else
  AGENT_CANON_CI_EVAL_LOG_DIR_VALUE="$(
    python3 "${AGENT_CANON_BOUNDARY_SCRIPT}" temp-dir \
      --root "${WORKSPACE_ROOT}" \
      --candidate "${WORKSPACE_ROOT}/.agent-canon/tmp" \
      --prefix run-all-eval \
      --purpose run-all-checks-eval-log
  )"
  AGENT_CANON_CI_EVAL_LOG_TEMP_CREATED=1
fi
AGENT_CANON_CI_SETUP_COMPLETE=1

PYTHON_BIN="${PYTHON_BIN:-}"
if [ -z "$PYTHON_BIN" ]; then
  if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
  elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="python"
  else
    echo "python3 or python is required to run CI checks" >&2
    exit 127
  fi
fi

# オプション解析
QUICK_MODE=0
SKIP_DOCS=0
SKIP_GITHUB_WORKFLOWS=0
SKIP_EXPERIMENTS=0
PR_GATE_RECEIPT=""
PR_GATE_RECEIPT_VALID=0
PR_GATE_DEPENDENCY_SOURCE_STATUS="not_applicable"
PR_GATE_PARENT_PID="${PPID}"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --quick)
      QUICK_MODE=1
      shift
      ;;
    --skip-docs)
      SKIP_DOCS=1
      shift
      ;;
    --skip-github-workflows)
      SKIP_GITHUB_WORKFLOWS=1
      shift
      ;;
    --skip-experiments)
      SKIP_EXPERIMENTS=1
      shift
      ;;
    --pr-gate-receipt)
      if [[ $# -lt 2 ]]; then
        echo "Missing value for --pr-gate-receipt" >&2
        exit 2
      fi
      PR_GATE_RECEIPT="$2"
      shift 2
      ;;
    --pr-gate-parent-pid)
      if [[ $# -lt 2 || ! "$2" =~ ^[1-9][0-9]*$ ]]; then
        echo "Missing or invalid value for --pr-gate-parent-pid" >&2
        exit 2
      fi
      PR_GATE_PARENT_PID="$2"
      shift 2
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 1
      ;;
  esac
done

validate_pr_gate_receipt() {
  if [[ ! -f "${PR_GATE_RECEIPT}" ]]; then
    echo "Invalid PR gate receipt: missing file" >&2
    return 1
  fi
  local validated_status=""
  if ! validated_status="$(python3 "${CANON_CI_ROOT}/pr_gate_receipt.py" validate \
    --receipt "${PR_GATE_RECEIPT}" \
    --root "${WORKSPACE_ROOT}" \
    --parent-pid "${PR_GATE_PARENT_PID}")"; then
    echo "Invalid PR gate receipt: source-owned receipt validation failed" >&2
    return 1
  fi
  case "${validated_status}" in
    status=source) PR_GATE_DEPENDENCY_SOURCE_STATUS=source ;;
    status=skipped) PR_GATE_DEPENDENCY_SOURCE_STATUS=skipped ;;
    *)
      echo "Invalid PR gate receipt: validator returned unexpected status" >&2
      return 1
      ;;
  esac
  return 0
}

if [[ -n "${PR_GATE_RECEIPT}" ]]; then
  if ! validate_pr_gate_receipt; then
    exit 1
  fi
  PR_GATE_RECEIPT_VALID=1
  echo "PR_GATE_RECEIPT=accepted dependency_source=${PR_GATE_DEPENDENCY_SOURCE_STATUS}"
fi

resolve_agent_canon_cli() {
  local root_tool_binary="${CANON_TOOLS_ROOT}/bin/agent-canon"
  local source_tool_binary="${AGENT_CANON_SOURCE_ROOT}/tools/bin/agent-canon"
  local source_release_binary="${AGENT_CANON_SOURCE_ROOT}/rust/agent-canon/target/release/agent-canon"
  local source_debug_binary="${AGENT_CANON_SOURCE_ROOT}/rust/agent-canon/target/debug/agent-canon"
  if [ -x "${source_tool_binary}" ]; then
    AGENT_CANON_CLI_MODE="binary"
    AGENT_CANON_CLI_CMD="${source_tool_binary}"
    return 0
  fi
  if [ -x "${source_release_binary}" ]; then
    AGENT_CANON_CLI_MODE="binary"
    AGENT_CANON_CLI_CMD="${source_release_binary}"
    return 0
  fi
  if [ -x "${source_debug_binary}" ]; then
    AGENT_CANON_CLI_MODE="binary"
    AGENT_CANON_CLI_CMD="${source_debug_binary}"
    return 0
  fi
  if [ -x "${root_tool_binary}" ]; then
    AGENT_CANON_CLI_MODE="binary"
    AGENT_CANON_CLI_CMD="${root_tool_binary}"
    return 0
  fi
  if command -v cargo >/dev/null 2>&1 && [ -f "${AGENT_CANON_CARGO_MANIFEST}" ]; then
    AGENT_CANON_CLI_MODE="cargo"
    AGENT_CANON_CLI_CMD="cargo"
    return 0
  fi
  return 1
}

run_agent_canon() {
  local command
  if [ "${AGENT_CANON_CLI_MODE:-}" = "binary" ] && [ -n "${AGENT_CANON_CLI_CMD:-}" ]; then
    command=("${AGENT_CANON_CLI_CMD}" "$@")
  elif [ "${AGENT_CANON_CLI_MODE:-}" = "cargo" ] && [ -n "${AGENT_CANON_CLI_CMD:-}" ]; then
    command=("${AGENT_CANON_CLI_CMD}" run --manifest-path "${AGENT_CANON_CARGO_MANIFEST}" -- "$@")
  else
    echo "AGENT_CANON_CLI_BLOCKER=agent_canon_cli_unavailable" >&2
    echo "AGENT_CANON_CLI_REASON=agent-canon CLI binary/shim missing and cargo route unavailable" >&2
    return 127
  fi
  python3 "${AGENT_CANON_BOUNDARY_SCRIPT}" exec-parent-bound \
    --root "${WORKSPACE_ROOT}" \
    --source-root "${AGENT_CANON_SOURCE_ROOT}" \
    -- "${command[@]}"
  return $?
}

if ! resolve_agent_canon_cli; then
  AGENT_CANON_CLI_MODE="missing"
  AGENT_CANON_CLI_CMD=""
fi
echo "AGENT_CANON_CLI_MODE=${AGENT_CANON_CLI_MODE}"
if [ -n "${AGENT_CANON_CLI_CMD:-}" ]; then
  echo "AGENT_CANON_CLI_PATH=${AGENT_CANON_CLI_CMD}"
fi

add_pythonpath() {
  local path="${1}"
  [ -z "${path}" ] && return
  case ":${RUN_ALL_CHECKS_PYTHONPATH}:" in
    *":${path}:"*)
      ;;
    *)
      if [ -z "${RUN_ALL_CHECKS_PYTHONPATH}" ]; then
        RUN_ALL_CHECKS_PYTHONPATH="${path}"
      else
        RUN_ALL_CHECKS_PYTHONPATH="${path}:${RUN_ALL_CHECKS_PYTHONPATH}"
      fi
      ;;
  esac
}

RUN_ALL_CHECKS_PYTHONPATH=""
add_pythonpath "${AGENT_CANON_SOURCE_ROOT}"
add_pythonpath "${AGENT_CANON_SOURCE_ROOT}/tools"
add_pythonpath "${AGENT_CANON_SOURCE_ROOT}/tools/agent_tools"
add_pythonpath "${WORKSPACE_ROOT}/python"
if [ -n "${PYTHONPATH:-}" ]; then
  IFS=':' read -r -a existing_pythonpath <<< "${PYTHONPATH}"
  for entry in "${existing_pythonpath[@]}"; do
    add_pythonpath "${entry}"
  done
fi
export PYTHONPATH="${RUN_ALL_CHECKS_PYTHONPATH}"
export JAX_PLATFORMS="${JAX_PLATFORMS:-}"
export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-}"
export NVIDIA_VISIBLE_DEVICES="${NVIDIA_VISIBLE_DEVICES:-}"
export GIT_AUTHOR_NAME="${GIT_AUTHOR_NAME:-AgentCanon CI}"
export GIT_AUTHOR_EMAIL="${GIT_AUTHOR_EMAIL:-agent-canon-ci@example.invalid}"
export GIT_COMMITTER_NAME="${GIT_COMMITTER_NAME:-AgentCanon CI}"
export GIT_COMMITTER_EMAIL="${GIT_COMMITTER_EMAIL:-agent-canon-ci@example.invalid}"

echo "════════════════════════════════════════════════════════════════"
echo "📋 統合 CI セッション開始"
echo "════════════════════════════════════════════════════════════════"
echo ""
echo "Python interpreter: ${PYTHON_BIN}"
echo "JAX test platform: ${JAX_PLATFORMS}"
echo "AgentCanon CI log archive: ${AGENT_CANON_CI_HOOK_ARCHIVE_DIR}"
echo ""

EXIT_CODE=0

if [ -f "${WORKSPACE_ROOT}/WORKTREE_SCOPE.md" ]; then
  echo "0️⃣a worktree scope / action-log checks を実行中..."
  if "$PYTHON_BIN" "${CANON_TOOLS_ROOT}/agent_tools/worktree_scope_lint.py" --current 2>&1; then
    echo "✅ worktree scope / action-log checks 成功"
  else
    echo "❌ worktree scope / action-log checks 失敗"
    EXIT_CODE=1
  fi
  echo ""
fi

# 0. agent/runtime sync checks
echo "0️⃣  agent/runtime sync checks を実行中..."
CANON_GRAPH_READY=0
if [ "$PR_GATE_RECEIPT_VALID" -eq 1 ]; then
  echo "⏭️ canonical graph build skipped: validated source receipt consumed"
elif run_agent_canon graph build --root "$WORKSPACE_ROOT" --profile default --format json; then
  CANON_GRAPH_READY=1
else
  echo "❌ canonical graph build 失敗"
  EXIT_CODE=1
fi
if "$PYTHON_BIN" "${CANON_TOOLS_ROOT}/agent_tools/smoke_test_research_perspective_pack.py" 2>&1; then
  echo "✅ research perspective pack smoke test 成功"
else
  echo "❌ research perspective pack smoke test 失敗"
  EXIT_CODE=1
fi
if [ "$PR_GATE_RECEIPT_VALID" -eq 1 ]; then
  echo "DEPENDENCY_HEADER_CHECKS=skip reason=validated_source_receipt_consumed"
elif [ "$CANON_GRAPH_READY" -eq 1 ]; then
  if "$PYTHON_BIN" "${CANON_TOOLS_ROOT}/agent_tools/check_dependency_headers.py" --changed 2>&1; then
    echo "✅ dependency header checks 成功"
  else
    echo "❌ dependency header checks 失敗"
    EXIT_CODE=1
  fi
else
  echo "⏭️ dependency header checks skipped: canonical graph build failed"
fi
if [ "$PR_GATE_RECEIPT_VALID" -eq 0 ]; then
  if bash "${CANON_TOOLS_ROOT}/agent_tools/check_dependency_header_format.sh" --changed 2>&1; then
    echo "✅ dependency manifest format checks 成功"
  else
    echo "❌ dependency manifest format checks 失敗"
    EXIT_CODE=1
  fi
fi
if "$PYTHON_BIN" "${CANON_TOOLS_ROOT}/agent_tools/check_static_any.py" 2>&1; then
  echo "✅ explicit Any static checks 成功"
else
  echo "❌ explicit Any static checks 失敗"
  EXIT_CODE=1
fi
if "$PYTHON_BIN" "${CANON_TOOLS_ROOT}/agent_tools/check_log_helper_names.py" --changed --exclude vendor --exclude reports 2>&1; then
  echo "✅ log helper naming checks 成功"
else
  echo "❌ log helper naming checks 失敗"
  EXIT_CODE=1
fi
if "$PYTHON_BIN" "${CANON_TOOLS_ROOT}/agent_tools/import_responsibility.py" --changed 2>&1; then
  echo "✅ import responsibility checks 成功"
else
  echo "❌ import responsibility checks 失敗"
  EXIT_CODE=1
fi
if "$PYTHON_BIN" "${CANON_TOOLS_ROOT}/validation/notebook_quality.py" --all 2>&1; then
  echo "✅ notebook quality checks 成功"
else
  echo "❌ notebook quality checks 失敗"
  EXIT_CODE=1
fi
if [ -d python ]; then
  if run_agent_canon python-algorithm-contract-check --root "$WORKSPACE_ROOT" python 2>&1; then
    echo "✅ Python algorithm contract checks 成功"
  else
    echo "❌ Python algorithm contract checks 失敗"
    EXIT_CODE=1
  fi
fi
if "$PYTHON_BIN" "${CANON_TOOLS_ROOT}/agent_tools/check_convention_compliance.py" 2>&1; then
  echo "✅ convention compliance wiring checks 成功"
else
  echo "❌ convention compliance wiring checks 失敗"
  EXIT_CODE=1
fi
if "$PYTHON_BIN" "${CANON_TOOLS_ROOT}/agent_tools/check_skill_frontmatter.py" 2>&1; then
  echo "✅ runtime skill frontmatter checks 成功"
else
  echo "❌ runtime skill frontmatter checks 失敗"
  EXIT_CODE=1
fi
if "$PYTHON_BIN" "${CANON_TOOLS_ROOT}/agent_tools/skill_tool_commands.py" check 2>&1; then
  echo "✅ runtime skill tool command checks 成功"
else
  echo "❌ runtime skill tool command checks 失敗"
  EXIT_CODE=1
fi
if "$PYTHON_BIN" "${CANON_TOOLS_ROOT}/agent_tools/tool_catalog.py" 2>&1; then
  echo "✅ tool catalog checks 成功"
else
  echo "❌ tool catalog checks 失敗"
  EXIT_CODE=1
fi
if "$PYTHON_BIN" "${CANON_TOOLS_ROOT}/agent_tools/tool_proof_coverage.py" 2>&1; then
  echo "✅ tool proof coverage checks 成功"
else
  echo "❌ tool proof coverage checks 失敗"
  EXIT_CODE=1
fi
if [ "$CANON_GRAPH_READY" -eq 1 ]; then
  if "$PYTHON_BIN" "${CANON_TOOLS_ROOT}/agent_tools/tool_drift.py" 2>&1; then
    echo "✅ tool/convention drift checks 成功"
  else
    echo "❌ tool/convention drift checks 失敗"
    EXIT_CODE=1
  fi
elif [ "$PR_GATE_RECEIPT_VALID" -eq 1 ]; then
  echo "⏭️ tool/convention drift checks skipped: validated source receipt consumed"
else
  echo "⏭️ tool/convention drift checks skipped: canonical graph build failed"
fi
if "$PYTHON_BIN" "${CANON_TOOLS_ROOT}/agent_tools/responsibility_scope.py" 2>&1; then
  echo "✅ responsibility scope checks 成功"
else
  echo "❌ responsibility scope checks 失敗"
  EXIT_CODE=1
fi
if "$PYTHON_BIN" "${CANON_TOOLS_ROOT}/agent_tools/issue_sync.py" 2>&1; then
  echo "✅ local issue sync checks 成功"
else
  echo "❌ local issue sync checks 失敗"
  EXIT_CODE=1
fi
if [[ "${AGENT_CANON_REPOSITORY_MODE}" == "standalone_source" ]]; then
  accumulated_eval_args=(--run-id run-all-checks --log-dir "${AGENT_CANON_CI_EVAL_LOG_DIR_VALUE}")
  if AGENT_CANON_HOOK_ARCHIVE_DIR="${AGENT_CANON_CI_HOOK_ARCHIVE_DIR}" \
    "$PYTHON_BIN" "${CANON_TOOLS_ROOT}/agent_tools/run_accumulated_agent_evals.py" "${accumulated_eval_args[@]}" 2>&1; then
    echo "✅ accumulated agent eval producers 成功"
  else
    echo "❌ accumulated agent eval producers 失敗"
    EXIT_CODE=1
  fi
  if AGENT_CANON_HOOK_ARCHIVE_DIR="${AGENT_CANON_CI_HOOK_ARCHIVE_DIR}" "$PYTHON_BIN" "${CANON_TOOLS_ROOT}/agent_tools/eval_accumulation_check.py" 2>&1; then
    echo "✅ eval accumulation checks 成功"
  else
    echo "❌ eval accumulation checks 失敗"
    EXIT_CODE=1
  fi
else
  echo "ACCUMULATED_AGENT_EVAL=skip reason=agentcanon_source_owned_gate"
  echo "EVAL_ACCUMULATION=skip reason=agentcanon_source_owned_gate"
fi
if cargo fmt --manifest-path "$AGENT_CANON_CARGO_MANIFEST" -- --check 2>&1; then
  echo "✅ Rust format checks 成功"
else
  echo "❌ Rust format checks 失敗"
  EXIT_CODE=1
fi
if cargo clippy --manifest-path "$AGENT_CANON_CARGO_MANIFEST" --all-targets -- -D warnings 2>&1; then
  echo "✅ Rust clippy checks 成功"
else
  echo "❌ Rust clippy checks 失敗"
  EXIT_CODE=1
fi
if cargo test --manifest-path "$AGENT_CANON_CARGO_MANIFEST" 2>&1; then
  echo "✅ Rust tests 成功"
else
  echo "❌ Rust tests 失敗"
  EXIT_CODE=1
fi
if [ "$SKIP_GITHUB_WORKFLOWS" -eq 1 ]; then
  echo "GITHUB_WORKFLOW_CHECKS=skip reason=already_checked_by_parent_gate"
elif "$PYTHON_BIN" "${CANON_CI_ROOT}/check_github_workflows.py" 2>&1; then
  echo "✅ GitHub workflow / PR template checks 成功"
else
  echo "❌ GitHub workflow / PR template checks 失敗"
  EXIT_CODE=1
fi
if "$PYTHON_BIN" "${CANON_CI_ROOT}/container_config.py" 2>&1; then
  echo "✅ container configuration checks 成功"
else
  echo "❌ container configuration checks 失敗"
  EXIT_CODE=1
fi
echo ""

# 1. Markdown / link checks
echo "1️⃣  documentation checks を実行中..."
if [ "$SKIP_DOCS" -eq 1 ]; then
  echo "DOCS_CHECKS=skip reason=already_checked_by_parent_gate"
elif run_agent_canon docs check 2>&1; then
  echo "✅ documentation checks 成功"
else
  echo "❌ documentation checks 失敗"
  EXIT_CODE=1
fi
echo ""

# 2. experiment registry checks
echo "2️⃣  experiment registry checks を実行中..."
if [ "$SKIP_EXPERIMENTS" -eq 1 ]; then
  echo "EXPERIMENT_REGISTRY=skip reason=skip_experiments_option"
  echo "experiment registry validation skipped by --skip-experiments"
elif [ ! -e experiments/registry.toml ]; then
  echo "EXPERIMENT_REGISTRY=skip"
  echo "experiment registry absent in this checkout; skipping registry validation"
elif "$PYTHON_BIN" "${CANON_CI_ROOT}/check_experiment_registry.py" 2>&1; then
  echo "✅ experiment registry checks 成功"
else
  echo "❌ experiment registry checks 失敗"
  EXIT_CODE=1
fi
echo ""

# 3. Python quality checks
python_quality_args=()
if [ "$QUICK_MODE" -eq 1 ]; then
  python_quality_args+=(--quick)
fi
if bash "${CANON_CI_ROOT}/run_python_quality_checks.sh" "${python_quality_args[@]}"; then
  echo "✅ Python quality checks 成功"
else
  echo "❌ Python quality checks 失敗"
  EXIT_CODE=1
fi
echo ""

echo "════════════════════════════════════════════════════════════════"
if [ $EXIT_CODE -eq 0 ]; then
  echo "✅ CI チェック完了: すべて成功"
else
  echo "❌ CI チェック完了: 失敗あり"
fi
echo "════════════════════════════════════════════════════════════════"

exit $EXIT_CODE
