#!/usr/bin/env bash
# @dependency-start
# responsibility Runs all checks CI automation.
# upstream implementation ../agent_tools/check_dependency_headers.py validates changed-file dependency manifests
# upstream implementation ../agent_tools/scan_dependency_headers.sh scans changed-file manifest coverage
# upstream implementation ../agent_tools/check_dependency_header_format.sh validates changed-file manifest syntax
# upstream implementation ../docs/mirror_skill_shims.py validates skill shim mirrors
# upstream implementation ../agent_tools/smoke_test_research_perspective_pack.py validates research role packet
# @dependency-end
set -euo pipefail

# ═══════════════════════════════════════════════════════════════════════════
# 統合 CI スクリプト
#
# 用途: agent/runtime・Markdown・pytest・pyright・pydocstyle・ruff を一括実行して
#       プロジェクト品質を検証
#
# 使用方法:
#   bash tools/ci/run_all_checks.sh           # 全テスト・解析実行
#   bash tools/ci/run_all_checks.sh --quick   # 高速モード（ruff skip）
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
while [[ $# -gt 0 ]]; do
  case "$1" in
    --quick)
      QUICK_MODE=1
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
export JAX_PLATFORMS="${JAX_PLATFORMS:-cpu}"
export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-}"
export NVIDIA_VISIBLE_DEVICES="${NVIDIA_VISIBLE_DEVICES:-}"

echo "════════════════════════════════════════════════════════════════"
echo "📋 統合 CI セッション開始"
echo "════════════════════════════════════════════════════════════════"
echo ""
echo "Python interpreter: ${PYTHON_BIN}"
echo "JAX test platform: ${JAX_PLATFORMS}"
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
if "$PYTHON_BIN" tools/docs/mirror_skill_shims.py --target .claude/skills --prune --check 2>&1; then
  echo "✅ skill mirror sync 成功"
else
  echo "❌ skill mirror sync 失敗"
  EXIT_CODE=1
fi
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
echo ""

# 1. Markdown / link checks
echo "1️⃣  documentation checks を実行中..."
if bash tools/ci/run_docs_checks.sh 2>&1; then
  echo "✅ documentation checks 成功"
else
  echo "❌ documentation checks 失敗"
  EXIT_CODE=1
fi
echo ""

# 2. experiment registry checks
echo "2️⃣  experiment registry checks を実行中..."
if "$PYTHON_BIN" tools/ci/check_experiment_registry.py 2>&1; then
  echo "✅ experiment registry checks 成功"
else
  echo "❌ experiment registry checks 失敗"
  EXIT_CODE=1
fi
echo ""

# 3. pytest 実行
echo "3️⃣  pytest を実行中..."
if "$PYTHON_BIN" -m pytest tests/ -q --tb=short 2>&1; then
  echo "✅ pytest 成功"
else
  echo "❌ pytest 失敗"
  EXIT_CODE=1
fi
echo ""

# 4. pyright 実行
echo "4️⃣  pyright を実行中..."
if "$PYTHON_BIN" -m pyright 2>&1; then
  echo "✅ pyright 成功"
else
  echo "❌ pyright 失敗"
  EXIT_CODE=1
fi
echo ""

# 5. pydocstyle 実行（Docstring 検証）
echo "5️⃣  pydocstyle を実行中... (Docstring チェック)"
if "$PYTHON_BIN" -m pydocstyle python tests 2>&1; then
  echo "✅ pydocstyle 成功"
else
  echo "❌ pydocstyle 失敗（詳細: documents/DOCSTRING_GUIDE.md を参照）"
  EXIT_CODE=1
fi
echo ""

# 5. ruff (QUICK_MODE でスキップ可能)
if [ $QUICK_MODE -eq 0 ]; then
  echo "6️⃣  ruff を実行中..."
  echo "   - E,F: コード品質（エラー・警告）"
  echo "   - I: Import 順序チェック"
  echo "   - D: Docstring 検証"
  echo "   - UP: Python 最新構文チェック"
  echo ""
  
  if "$PYTHON_BIN" -m ruff check python tests --select D,E,F,I,UP 2>&1; then
    echo "✅ ruff 成功"
  else
    echo "❌ ruff 失敗"
    EXIT_CODE=1
  fi
  echo ""
fi

echo "════════════════════════════════════════════════════════════════"
if [ $EXIT_CODE -eq 0 ]; then
  echo "✅ CI チェック完了: すべて成功"
else
  echo "❌ CI チェック完了: 失敗あり"
fi
echo "════════════════════════════════════════════════════════════════"

exit $EXIT_CODE
