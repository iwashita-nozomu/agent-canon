#!/usr/bin/env bash
# @dependency-start
# contract tool
# responsibility Runs all checks CI automation.
# upstream implementation ../agent_tools/check_dependency_headers.py validates changed-file dependency manifests
# upstream implementation ../agent_tools/scan_dependency_headers.sh scans changed-file manifest coverage
# upstream implementation ../agent_tools/check_dependency_header_format.sh validates changed-file manifest syntax
# upstream implementation ../agent_tools/check_hardcoded_numbers.py validates changed-source numeric literals
# upstream implementation ../agent_tools/check_static_any.py rejects explicit Python Any usage
# upstream implementation ../agent_tools/check_log_helper_names.py validates log helper naming
# upstream implementation ../agent_tools/import_responsibility.py validates import ownership boundaries
# upstream implementation ../validation/notebook_quality.py validates notebooks as readable runnable demos
# upstream implementation ../agent_tools/check_algorithm_module_nested_contract.py validates nested algorithm ownership
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
# upstream implementation ../../rust/agent-canon/src/local_llm.rs validates Rust local LLM CLI routing
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
#       pytest, pyright, pydocstyle, and ruff checks を一括実行します。
#       普段の変更では Makefile の check-matrix から対象 profile を選び、
#       この script は full confidence gate として使います。
#
# 使用方法:
#   bash tools/ci/run_all_checks.sh           # full confidence checks
#   bash tools/ci/run_all_checks.sh --quick   # broad checks with ruff skipped
#   bash tools/ci/run_all_checks.sh --quick --skip-docs --skip-github-workflows
#                                               # PR gate reuse after those gates already ran
#   bash tools/ci/run_all_checks.sh --verbose # 詳細出力
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
#   - documents/REVIEW_PROCESS.md: review と validation の正本
#   - .github/workflows/ci.yml: GitHub Actions ワークフロー
#
# ═══════════════════════════════════════════════════════════════════════════

WORKSPACE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$WORKSPACE_ROOT"

AGENT_CANON_SOURCE_ROOT="$WORKSPACE_ROOT"
if [ ! -f "${AGENT_CANON_SOURCE_ROOT}/rust/agent-canon/Cargo.toml" ] \
  && [ -f "${WORKSPACE_ROOT}/vendor/agent-canon/rust/agent-canon/Cargo.toml" ]; then
  AGENT_CANON_SOURCE_ROOT="${WORKSPACE_ROOT}/vendor/agent-canon"
fi
AGENT_CANON_CARGO_MANIFEST="${AGENT_CANON_SOURCE_ROOT}/rust/agent-canon/Cargo.toml"
AGENT_CANON_CI_HOOK_ARCHIVE_DIR="${AGENT_CANON_HOOK_ARCHIVE_DIR:-${AGENT_CANON_SOURCE_ROOT}/.agent-canon/log-archive}"
mkdir -p "${AGENT_CANON_CI_HOOK_ARCHIVE_DIR}"
if [ -n "${AGENT_CANON_CI_EVAL_LOG_DIR:-}" ]; then
  AGENT_CANON_CI_EVAL_LOG_DIR_VALUE="${AGENT_CANON_CI_EVAL_LOG_DIR}"
else
  AGENT_CANON_CI_EVAL_LOG_DIR_VALUE="${WORKSPACE_ROOT}/.state/agent-eval-runs/run-all-checks"
  rm -rf "${AGENT_CANON_CI_EVAL_LOG_DIR_VALUE}"
  mkdir -p "${AGENT_CANON_CI_EVAL_LOG_DIR_VALUE}"
fi

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
VERBOSE_MODE=0
SKIP_DOCS=0
SKIP_GITHUB_WORKFLOWS=0
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
    --verbose)
      VERBOSE_MODE=1
      shift
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 1
      ;;
  esac
done

export PYTHONPATH="${WORKSPACE_ROOT}/python:${PYTHONPATH:-}"
export JAX_PLATFORMS="${JAX_PLATFORMS:-}"
export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-}"
export NVIDIA_VISIBLE_DEVICES="${NVIDIA_VISIBLE_DEVICES:-}"
export GIT_AUTHOR_NAME="${GIT_AUTHOR_NAME:-AgentCanon CI}"
export GIT_AUTHOR_EMAIL="${GIT_AUTHOR_EMAIL:-agent-canon-ci@example.invalid}"
export GIT_COMMITTER_NAME="${GIT_COMMITTER_NAME:-AgentCanon CI}"
export GIT_COMMITTER_EMAIL="${GIT_COMMITTER_EMAIL:-agent-canon-ci@example.invalid}"

if ! command -v cargo >/dev/null 2>&1 && [ -f "${HOME}/.cargo/env" ]; then
  # shellcheck disable=SC1091
  . "${HOME}/.cargo/env"
fi

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
  if "$PYTHON_BIN" tools/agent_tools/worktree_scope_lint.py --current 2>&1; then
    echo "✅ worktree scope / action-log checks 成功"
  else
    echo "❌ worktree scope / action-log checks 失敗"
    EXIT_CODE=1
  fi
  echo ""
fi

# 0. agent/runtime sync checks
echo "0️⃣  agent/runtime sync checks を実行中..."
if "$PYTHON_BIN" tools/agent_tools/smoke_test_research_perspective_pack.py 2>&1; then
  echo "✅ research perspective pack smoke test 成功"
else
  echo "❌ research perspective pack smoke test 失敗"
  EXIT_CODE=1
fi
if "$PYTHON_BIN" tools/agent_tools/check_dependency_headers.py --changed 2>&1; then
  echo "✅ dependency header checks 成功"
else
  echo "❌ dependency header checks 失敗"
  EXIT_CODE=1
fi
if bash tools/agent_tools/scan_dependency_headers.sh --changed 2>&1; then
  echo "✅ dependency manifest scan 成功"
else
  echo "❌ dependency manifest scan 失敗"
  EXIT_CODE=1
fi
if bash tools/agent_tools/check_dependency_header_format.sh --changed 2>&1; then
  echo "✅ dependency manifest format checks 成功"
else
  echo "❌ dependency manifest format checks 失敗"
  EXIT_CODE=1
fi
if "$PYTHON_BIN" tools/agent_tools/check_hardcoded_numbers.py --changed --exclude tests --exclude vendor --exclude reports 2>&1; then
  echo "✅ hardcoded numeric literal checks 成功"
else
  echo "❌ hardcoded numeric literal checks 失敗"
  EXIT_CODE=1
fi
if "$PYTHON_BIN" tools/agent_tools/check_static_any.py 2>&1; then
  echo "✅ explicit Any static checks 成功"
else
  echo "❌ explicit Any static checks 失敗"
  EXIT_CODE=1
fi
if "$PYTHON_BIN" tools/agent_tools/check_log_helper_names.py --changed --exclude vendor --exclude reports 2>&1; then
  echo "✅ log helper naming checks 成功"
else
  echo "❌ log helper naming checks 失敗"
  EXIT_CODE=1
fi
if "$PYTHON_BIN" tools/agent_tools/import_responsibility.py --changed 2>&1; then
  echo "✅ import responsibility checks 成功"
else
  echo "❌ import responsibility checks 失敗"
  EXIT_CODE=1
fi
if "$PYTHON_BIN" tools/validation/notebook_quality.py --all 2>&1; then
  echo "✅ notebook quality checks 成功"
else
  echo "❌ notebook quality checks 失敗"
  EXIT_CODE=1
fi
if [ -d python ]; then
  if "$PYTHON_BIN" tools/agent_tools/check_algorithm_module_nested_contract.py python 2>&1; then
    echo "✅ algorithm module nested contract checks 成功"
  else
    echo "❌ algorithm module nested contract checks 失敗"
    EXIT_CODE=1
  fi
fi
if "$PYTHON_BIN" tools/agent_tools/check_convention_compliance.py 2>&1; then
  echo "✅ convention compliance wiring checks 成功"
else
  echo "❌ convention compliance wiring checks 失敗"
  EXIT_CODE=1
fi
if "$PYTHON_BIN" tools/agent_tools/check_skill_frontmatter.py 2>&1; then
  echo "✅ runtime skill frontmatter checks 成功"
else
  echo "❌ runtime skill frontmatter checks 失敗"
  EXIT_CODE=1
fi
if "$PYTHON_BIN" tools/agent_tools/skill_tool_commands.py check 2>&1; then
  echo "✅ runtime skill tool command checks 成功"
else
  echo "❌ runtime skill tool command checks 失敗"
  EXIT_CODE=1
fi
if "$PYTHON_BIN" tools/agent_tools/tool_catalog.py 2>&1; then
  echo "✅ tool catalog checks 成功"
else
  echo "❌ tool catalog checks 失敗"
  EXIT_CODE=1
fi
if "$PYTHON_BIN" tools/agent_tools/tool_proof_coverage.py 2>&1; then
  echo "✅ tool proof coverage checks 成功"
else
  echo "❌ tool proof coverage checks 失敗"
  EXIT_CODE=1
fi
if "$PYTHON_BIN" tools/agent_tools/tool_drift.py 2>&1; then
  echo "✅ tool/convention drift checks 成功"
else
  echo "❌ tool/convention drift checks 失敗"
  EXIT_CODE=1
fi
if "$PYTHON_BIN" tools/agent_tools/responsibility_scope.py 2>&1; then
  echo "✅ responsibility scope checks 成功"
else
  echo "❌ responsibility scope checks 失敗"
  EXIT_CODE=1
fi
if "$PYTHON_BIN" tools/agent_tools/issue_sync.py 2>&1; then
  echo "✅ local issue sync checks 成功"
else
  echo "❌ local issue sync checks 失敗"
  EXIT_CODE=1
fi
accumulated_eval_args=(--run-id run-all-checks --log-dir "${AGENT_CANON_CI_EVAL_LOG_DIR_VALUE}")
if AGENT_CANON_HOOK_ARCHIVE_DIR="${AGENT_CANON_CI_HOOK_ARCHIVE_DIR}" \
  "$PYTHON_BIN" tools/agent_tools/run_accumulated_agent_evals.py "${accumulated_eval_args[@]}" 2>&1; then
  echo "✅ accumulated agent eval producers 成功"
else
  echo "❌ accumulated agent eval producers 失敗"
  EXIT_CODE=1
fi
if AGENT_CANON_HOOK_ARCHIVE_DIR="${AGENT_CANON_CI_HOOK_ARCHIVE_DIR}" "$PYTHON_BIN" tools/agent_tools/eval_accumulation_check.py 2>&1; then
  echo "✅ eval accumulation checks 成功"
else
  echo "❌ eval accumulation checks 失敗"
  EXIT_CODE=1
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
elif "$PYTHON_BIN" tools/ci/check_github_workflows.py 2>&1; then
  echo "✅ GitHub workflow / PR template checks 成功"
else
  echo "❌ GitHub workflow / PR template checks 失敗"
  EXIT_CODE=1
fi
if "$PYTHON_BIN" tools/ci/container_config.py 2>&1; then
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
elif tools/bin/agent-canon docs check 2>&1; then
  echo "✅ documentation checks 成功"
else
  echo "❌ documentation checks 失敗"
  EXIT_CODE=1
fi
echo ""

# 2. experiment registry checks
echo "2️⃣  experiment registry checks を実行中..."
if [ ! -e experiments/registry.toml ]; then
  echo "EXPERIMENT_REGISTRY=skip"
  echo "experiment registry absent in this checkout; skipping registry validation"
elif "$PYTHON_BIN" tools/ci/check_experiment_registry.py 2>&1; then
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
if bash tools/ci/run_python_quality_checks.sh "${python_quality_args[@]}"; then
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
