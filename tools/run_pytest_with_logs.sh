#!/usr/bin/env bash
# @dependency-start
# contract tool
# responsibility Provides run pytest with logs repository automation.
# upstream design README.md shared automation index
# @dependency-end

set -euo pipefail

# このスクリプトは pytest のログを外部 runtime root の実行ごとの
# ディレクトリに保存します。source checkout 内にはログを作成しません。
# Python bytecode and child-process temporary files are runtime artifacts too.
# Disable implicit source-local bytecode before importing the boundary helper;
# the helper itself must not create a source-tree cache while resolving roots.
export PYTHONDONTWRITEBYTECODE=1

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-}"
if [ -z "${PYTHON_BIN}" ]; then
  if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python3)"
  elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python)"
  else
    echo "python3 or python is required" >&2
    exit 127
  fi
fi
export PYTHONPATH="${ROOT_DIR}/python${PYTHONPATH:+:${PYTHONPATH}}"

RUNTIME_ROOT="$({
  ROOT_DIR="${ROOT_DIR}" PYTHON_BIN="${PYTHON_BIN}" "${PYTHON_BIN}" - <<'PY'
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.environ["ROOT_DIR"])
from tools.agent_tools.runtime_artifacts import (  # noqa: E402
    RuntimeArtifactError,
    runtime_artifact_boundary,
)

try:
    boundary = runtime_artifact_boundary(
        Path(os.environ["ROOT_DIR"]),
        os.environ.get("AGENT_CANON_RUNTIME_ROOT"),
        create=True,
    )
    parent = boundary.ensure_directory(Path("tasks") / "pytest")
    print(tempfile.mkdtemp(prefix="run-", dir=str(parent)))
except RuntimeArtifactError as exc:
    print(f"runtime_root_error: {exc}", file=sys.stderr)
    raise SystemExit(2)
PY
} )"
RUN_DIR="${RUNTIME_ROOT}"
RAW_LOG="${RUN_DIR}/pytest.raw.txt"
JSON_LOG="${RUN_DIR}/pytest.jsonl"

# Keep every common Python/test cache and temporary file in this invocation's
# external directory.  Do not inherit a caller's source-relative TMPDIR or
# cache configuration.
TMP_DIR="${RUN_DIR}/tmp"
XDG_CACHE_DIR="${RUN_DIR}/xdg-cache"
mkdir -p "${TMP_DIR}" "${XDG_CACHE_DIR}"
export TMPDIR="${TMP_DIR}"
export TMP="${TMP_DIR}"
export TEMP="${TMP_DIR}"
export XDG_CACHE_HOME="${XDG_CACHE_DIR}"

pytest_args=("$@")
if [[ "${#pytest_args[@]}" -eq 0 ]]; then
  pytest_args=(tests/ -q --tb=short)
fi
# Pytest's cache is runtime output too; keep it beside the captured logs.
pytest_args+=("-o" "cache_dir=${RUN_DIR}/pytest-cache")

cd "${ROOT_DIR}"

set +e
set -o pipefail
"${PYTHON_BIN}" -m pytest "${pytest_args[@]}" 2>&1 | tee "${RAW_LOG}"
EXIT_CODE=${PIPESTATUS[0]}
set +o pipefail
set -e

RAW_LOG_PATH="${RAW_LOG}" JSON_LOG_PATH="${JSON_LOG}" "${PYTHON_BIN}" - << 'PY'
import json
import os
from pathlib import Path

raw_log = Path(os.environ["RAW_LOG_PATH"])
json_log = Path(os.environ["JSON_LOG_PATH"])

with raw_log.open() as f_in, json_log.open("w") as f_out:
    for line in f_in:
        stripped = line.strip()
        if not stripped:
            continue
        try:
            obj = json.loads(stripped)
        except Exception:
            continue
        if isinstance(obj, dict):
            f_out.write(json.dumps(obj) + "\n")
PY

echo "${EXIT_CODE}" > "${RUN_DIR}/exit_code.txt"

echo "logs_dir=${RUN_DIR}"
exit "${EXIT_CODE}"
