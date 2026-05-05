#!/usr/bin/env bash
# @dependency-start
# upstream implementation README.md directory index and local context contract
# @dependency-end
set -euo pipefail

# JSONL を Markdown に変換します。
# 使い方: jsonl_to_md.sh <input.jsonl> <output.md>

if [ "$#" -lt 2 ]; then
	echo "Usage: $0 <input.jsonl> <output.md>" >&2
	exit 1
fi

INPUT_PATH="$1"
OUTPUT_PATH="$2"

if [ ! -f "${INPUT_PATH}" ]; then
	echo "Input not found: ${INPUT_PATH}" >&2
	exit 1
fi

OUTPUT_DIR="$(dirname "${OUTPUT_PATH}")"
mkdir -p "${OUTPUT_DIR}"

INPUT_PATH="${INPUT_PATH}" OUTPUT_PATH="${OUTPUT_PATH}" /usr/bin/python3 - << 'PY'
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Tuple

input_path = Path(os.environ["INPUT_PATH"])
output_path = Path(os.environ["OUTPUT_PATH"])

preferred_keys = [
    "case",
    "source_file",
    "test",
    "func",
    "event",
    "iter",
    "step",
    "num_iter",
]


def format_value(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def ordered_items(obj: Dict[str, Any]) -> List[Tuple[str, Any]]:
    items: List[Tuple[str, Any]] = []
    used = set()
    for key in preferred_keys:
        if key in obj:
            items.append((key, obj[key]))
            used.add(key)
    for key in sorted(k for k in obj.keys() if k not in used):
        items.append((key, obj[key]))
    return items


with input_path.open() as f_in, output_path.open("w") as f_out:
    f_out.write(f"# JSONL レポート\n\n")
    f_out.write(f"- input: `{input_path}`\n")
    f_out.write("\n")

    index = 0
    for line in f_in:
        stripped = line.strip()
        if not stripped:
            continue
        try:
            obj = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue

        index += 1
        title = obj.get("case", f"record-{index}")
        f_out.write(f"## {title}\n\n")
        f_out.write("| key | value |\n")
        f_out.write("| --- | --- |\n")
        for key, value in ordered_items(obj):
            val = format_value(value)
            val = val.replace("|", "\\|")
            f_out.write(f"| {key} | {val} |\n")
        f_out.write("\n")
PY


echo "written: ${OUTPUT_PATH}"
