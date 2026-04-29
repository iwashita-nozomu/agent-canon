#!/usr/bin/env bash
# @dependency-start
# responsibility Provides run pytest with logs repository automation.
# upstream design README.md shared automation index
# @dependency-end

set -euo pipefail

# このスクリプトは pytest のログを実行ごとのディレクトリに保存します。
# 保存場所は tests/logs/[YYYYMMDD]-[HHMMSS]/ です。

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_ROOT="${ROOT_DIR}/tests/logs"
RUN_DIR="${LOG_ROOT}/[$(date +%Y%m%d)]-[$(date +%H%M%S)]"
RAW_LOG="${RUN_DIR}/pytest.raw.txt"
JSON_LOG="${RUN_DIR}/pytest.jsonl"

export PYTHONPATH="${ROOT_DIR}/python${PYTHONPATH:+:${PYTHONPATH}}"

mkdir -p "${RUN_DIR}"

pytest_args=("$@")
if [[ "${#pytest_args[@]}" -eq 0 ]]; then
  pytest_args=(tests/ -q --tb=short)
fi

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
