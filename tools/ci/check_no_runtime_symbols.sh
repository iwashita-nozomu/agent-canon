#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 3 ]]; then
  echo "usage: $0 <nm-path> <forbidden-symbol> <binary> [<binary> ...]" >&2
  exit 2
fi

NM_PATH="$1"
FORBIDDEN_SYMBOL="$2"
shift 2

for binary_path in "$@"; do
  if [[ ! -f "${binary_path}" ]]; then
    echo "missing binary: ${binary_path}" >&2
    exit 1
  fi
  if "${NM_PATH}" -C "${binary_path}" | grep -q "${FORBIDDEN_SYMBOL}"; then
    echo "forbidden symbol '${FORBIDDEN_SYMBOL}' found in ${binary_path}" >&2
    exit 1
  fi
done
