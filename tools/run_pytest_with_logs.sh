#!/usr/bin/env bash
# @dependency-start
# contract tool
# responsibility Provides run pytest with logs repository automation.
# upstream design README.md shared automation index
# @dependency-end

set -euo pipefail

# このスクリプトは pytest のログを外部 runtime root の実行ごとの
# ディレクトリに保存します。source checkout 内にはログを作成しません。

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-/usr/bin/python3}"
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

pytest_args=("$@")
if [[ "${#pytest_args[@]}" -eq 0 ]]; then
  pytest_args=(tests/ -q --tb=short)
fi
# Pytest's cache is runtime output too; keep it beside the captured logs.
pytest_args+=("-o" "cache_dir=${RUN_DIR}/pytest-cache")

cd "${ROOT_DIR}"

set +e
set -o pipefail
/usr/bin/python3 -m pytest "${pytest_args[@]}" 2>&1 | tee "${RAW_LOG}"
EXIT_CODE=${PIPESTATUS[0]}
set +o pipefail
set -e

RAW_LOG_PATH="${RAW_LOG}" JSON_LOG_PATH="${JSON_LOG}" /usr/bin/python3 - << 'PY'
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
