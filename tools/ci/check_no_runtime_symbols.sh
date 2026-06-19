#!/usr/bin/env bash
# @dependency-start
# contract tool
# responsibility Checks that compiled artifacts do not expose forbidden runtime symbols.
# upstream design ../README.md shared automation index
# downstream design ../../documents/cpp-build-layout.md describes native smoke-test entrypoints that may use this helper
# @dependency-end

set -euo pipefail

if [ "$#" -ne 3 ]; then
  echo "usage: $0 <nm> <forbidden-symbol> <artifact>" >&2
  exit 2
fi

NM_BIN="$1"
FORBIDDEN_SYMBOL="$2"
ARTIFACT="$3"

if [ -z "$NM_BIN" ] || [ "$NM_BIN" = "CMAKE_NM-NOTFOUND" ]; then
  echo "nm executable is required" >&2
  exit 2
fi

if [ -z "$FORBIDDEN_SYMBOL" ]; then
  echo "forbidden symbol is required" >&2
  exit 2
fi

if [ ! -x "$NM_BIN" ]; then
  echo "nm executable not found or not executable: $NM_BIN" >&2
  exit 2
fi

if [ ! -f "$ARTIFACT" ]; then
  echo "artifact not found: $ARTIFACT" >&2
  exit 2
fi

symbol_lines="$(
  {
    "$NM_BIN" -A "$ARTIFACT" 2>/dev/null || true
    "$NM_BIN" -D -A "$ARTIFACT" 2>/dev/null || true
  } | grep -F -- "$FORBIDDEN_SYMBOL" || true
)"

if [ -n "$symbol_lines" ]; then
  echo "forbidden runtime symbol found in $ARTIFACT: $FORBIDDEN_SYMBOL" >&2
  printf '%s\n' "$symbol_lines" >&2
  exit 1
fi

echo "forbidden runtime symbol absent: $FORBIDDEN_SYMBOL"
