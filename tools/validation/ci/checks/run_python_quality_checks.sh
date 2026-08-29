#!/usr/bin/env bash
# @dependency-start
# contract tool
# responsibility Runs shared Python syntax and static quality checks for CI and pre-review gates.
# upstream design ../README.md shared automation index
# upstream design ../../documents/conventions/DOCSTRING_GUIDE.md explicit Docstring review convention
# downstream implementation ./run_all_checks.sh calls this runner for Python checks
# downstream implementation ./pre_review.sh calls this runner before role write-scope enforcement
# @dependency-end
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
source "${SCRIPT_DIR}/../lib/repo_paths.sh"
WORKSPACE_ROOT="$(agent_canon_repo_root "${BASH_SOURCE[0]}")"
CANON_TOOLS_ROOT="$(agent_canon_source_tools_root "$WORKSPACE_ROOT")"
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
for candidate_path in python "${CANON_TOOLS_ROOT}/agent_tools" "${CANON_TOOLS_ROOT}" .codex/hooks; do
  if [ -d "${candidate_path}" ]; then
    PYTHON_IMPORT_PATHS+=("${candidate_path}")
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
  PYTHON_SOURCE_PATHS+=(python)
  if [ -d tests ]; then
    while IFS= read -r candidate_path; do
      PYTHON_SOURCE_PATHS+=("$candidate_path")
      PYTHON_TEST_PATHS+=("$candidate_path")
    done < <(
      find tests \
        -type f \( -name 'test_*.py' -o -name '*_test.py' \) -print | sort
    )
  fi
else
  AGENT_CANON_W2_OWNER_PATHS=(
    "${CANON_TOOLS_ROOT}/agent_tools/review_dispatch.py" \
    "${CANON_TOOLS_ROOT}/agent_tools/artifact_identity.py" \
    "${CANON_TOOLS_ROOT}/agent_tools/external_artifact_binding.py" \
    "${CANON_TOOLS_ROOT}/agent_tools/publication_integrator.py" \
    "${CANON_TOOLS_ROOT}/agent_tools/report_artifact_checks.py" \
    "${CANON_TOOLS_ROOT}/agent_tools/review_dispatch.py" \
    "${CANON_TOOLS_ROOT}/agent_tools/work_log.py" \
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
if [ ${#PYTHON_TEST_PATHS[@]} -eq 0 ]; then
  echo "PYTEST=skip reason=no_parent_owned_tests"
elif "$PYTHON_BIN" -m pytest "${PYTHON_TEST_PATHS[@]}" -q --tb=short 2>&1; then
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
