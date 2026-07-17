#!/usr/bin/env bash
# @dependency-start
# contract tool
# responsibility Runs shared Python quality checks for CI and pre-review gates.
# upstream design ../README.md shared automation index
# downstream implementation ./run_all_checks.sh calls this runner for Python checks
# downstream implementation ./pre_review.sh calls this runner before role write-scope enforcement
# @dependency-end
set -euo pipefail

WORKSPACE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${WORKSPACE_ROOT}"

PYTHON_BIN="${PYTHON_BIN:-}"
if [ -z "$PYTHON_BIN" ]; then
  if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
  elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="python"
  else
    echo "python3 or python is required to run Python quality checks" >&2
    exit 127
  fi
fi

QUICK_MODE=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --quick)
      QUICK_MODE=1
      shift
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 1
      ;;
  esac
done

PYTHON_IMPORT_PATHS=()
for candidate_path in python tools/agent_tools tools .codex/hooks; do
  if [ -d "${candidate_path}" ]; then
    PYTHON_IMPORT_PATHS+=("${WORKSPACE_ROOT}/${candidate_path}")
  fi
done
if [ ${#PYTHON_IMPORT_PATHS[@]} -gt 0 ]; then
  PYTHONPATH_VALUE="${PYTHON_IMPORT_PATHS[0]}"
  for ((path_index = 1; path_index < ${#PYTHON_IMPORT_PATHS[@]}; path_index++)); do
    PYTHONPATH_VALUE+=":${PYTHON_IMPORT_PATHS[path_index]}"
  done
  if [ -n "${PYTHONPATH:-}" ]; then
    PYTHONPATH_VALUE+=":${PYTHONPATH}"
  fi
  export PYTHONPATH="${PYTHONPATH_VALUE}"
fi
export JAX_PLATFORMS="${JAX_PLATFORMS:-}"
export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-}"
export NVIDIA_VISIBLE_DEVICES="${NVIDIA_VISIBLE_DEVICES:-}"

PYTHON_SOURCE_PATHS=()
PYTHON_TEST_PATHS=()
if [ -d python ]; then
  for candidate_path in python tests; do
    if [ -d "${candidate_path}" ]; then
      PYTHON_SOURCE_PATHS+=("${candidate_path}")
    fi
  done
  if [ -d tests ]; then
    PYTHON_TEST_PATHS+=(tests)
  fi
else
  AGENT_CANON_W2_OWNER_PATHS=(
    .codex/hooks/completion_review_guard.py \
    tools/agent_tools/artifact_identity.py \
    tools/agent_tools/external_artifact_binding.py \
    tools/agent_tools/publication_integrator.py \
    tools/agent_tools/report_artifact_checks.py \
    tools/agent_tools/review_dispatch.py \
    tools/agent_tools/work_log.py \
    tests/agent_tools/test_artifact_identity.py \
    tests/agent_tools/test_codex_hooks.py \
    tests/agent_tools/test_external_artifact_binding.py \
    tests/agent_tools/test_publication_integrator.py \
    tests/agent_tools/test_review_dispatch.py \
    tests/agent_tools/test_work_log.py
  )
  for candidate_path in "${AGENT_CANON_W2_OWNER_PATHS[@]}"; do
    if [ -f "${candidate_path}" ]; then
      PYTHON_SOURCE_PATHS+=("${candidate_path}")
    else
      echo "Missing canonical AgentCanon W2 owner path: ${candidate_path}" >&2
      exit 1
    fi
  done
  PYTHON_TEST_PATHS=(
    tests/agent_tools/test_artifact_identity.py
    tests/agent_tools/test_codex_hooks.py
    tests/agent_tools/test_external_artifact_binding.py
    tests/agent_tools/test_publication_integrator.py
    tests/agent_tools/test_review_dispatch.py
    tests/agent_tools/test_work_log.py
  )
fi

EXIT_CODE=0

echo "3️⃣  pytest を実行中..."
if "$PYTHON_BIN" -m pytest "${PYTHON_TEST_PATHS[@]}" -q --tb=short 2>&1; then
  echo "✅ pytest 成功"
else
  echo "❌ pytest 失敗"
  EXIT_CODE=1
fi
echo ""

echo "4️⃣  pyright を実行中..."
if "$PYTHON_BIN" -m pyright "${PYTHON_SOURCE_PATHS[@]}" 2>&1; then
  echo "✅ pyright 成功"
else
  echo "❌ pyright 失敗"
  EXIT_CODE=1
fi
echo ""

echo "5️⃣  pydocstyle を実行中... (Docstring チェック)"
if [ ${#PYTHON_SOURCE_PATHS[@]} -eq 0 ]; then
  echo "PYDOCSTYLE=skip"
  echo "AgentCanon Python source roots are absent in this checkout; skipping pydocstyle"
elif "$PYTHON_BIN" -m pydocstyle "${PYTHON_SOURCE_PATHS[@]}" 2>&1; then
  echo "✅ pydocstyle 成功"
else
  echo "❌ pydocstyle 失敗（詳細: documents/DOCSTRING_GUIDE.md を参照）"
  EXIT_CODE=1
fi
echo ""

if [ "$QUICK_MODE" -eq 1 ]; then
  echo "RUFF=skip reason=quick_mode"
elif [ ${#PYTHON_SOURCE_PATHS[@]} -eq 0 ]; then
  echo "RUFF=skip"
  echo "AgentCanon Python source roots are absent in this checkout; skipping ruff"
else
  echo "6️⃣  ruff を実行中..."
  echo "   - E,F: コード品質（エラー・警告）"
  echo "   - I: Import 順序チェック"
  echo "   - D: Docstring 検証"
  echo "   - UP: Python 最新構文チェック"
  echo ""
  if "$PYTHON_BIN" -m ruff check "${PYTHON_SOURCE_PATHS[@]}" --select D,E,F,I,UP --ignore E501 2>&1; then
    echo "✅ ruff 成功"
  else
    echo "❌ ruff 失敗"
    EXIT_CODE=1
  fi
fi
echo ""

if [ "$EXIT_CODE" -eq 0 ]; then
  echo "PYTHON_QUALITY_CHECKS=pass"
else
  echo "PYTHON_QUALITY_CHECKS=fail"
fi

exit "$EXIT_CODE"
