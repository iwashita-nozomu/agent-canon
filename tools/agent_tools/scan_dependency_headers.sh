#!/usr/bin/env bash
# @dependency-start
# contract tool
# responsibility Reports dependency-manifest coverage from the canonical parent graph.
# upstream design ../../documents/dependency-manifest-design.md dependency manifest DSL design
# upstream implementation ../../rust/agent-canon/src/graph.rs owns manifest parsing and graph materialization
# downstream implementation ./check_dependency_header_format.sh consumes the same graph capture
# @dependency-end
set -euo pipefail

ROOT_DIR="$(git -C "$PWD" rev-parse --show-toplevel 2>/dev/null || pwd)"
FAIL_MISSING=0
CHANGED=0
EXPLAIN_MISSING=0
declare -a INPUT_PATHS=()

usage() {
  cat <<'EOF'
Usage:
  scan_dependency_headers.sh [--root DIR] [--changed] [--fail-missing] [--allow-frontmatter] [--explain-missing] [paths...]

Reports canonical graph source nodes whose parsed manifest is absent.
Without --fail-missing this command is report-only.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --root) ROOT_DIR="$2"; shift 2 ;;
    --changed) CHANGED=1; shift ;;
    --fail-missing) FAIL_MISSING=1; shift ;;
    --allow-frontmatter) shift ;;
    --explain-missing) EXPLAIN_MISSING=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) INPUT_PATHS+=("${1#./}"); shift ;;
  esac
done

ROOT_DIR="$(realpath -m "$ROOT_DIR")"
if [[ -x "$ROOT_DIR/vendor/agent-canon/tools/bin/agent-canon" ]]; then
  GRAPH_CLI="$ROOT_DIR/vendor/agent-canon/tools/bin/agent-canon"
else
  GRAPH_CLI="$ROOT_DIR/tools/bin/agent-canon"
fi

status_file="$(mktemp)"
query_file="$(mktemp)"
selected_file="$(mktemp)"
trap 'rm -f "$status_file" "$query_file" "$selected_file"' EXIT

set +e
"$GRAPH_CLI" graph status --root "$ROOT_DIR" --profile default --format json >"$status_file"
status_exit=$?
set -e
if [[ "$status_exit" -ne 0 || "$(jq -r '.status // "invalid"' "$status_file" 2>/dev/null)" != "fresh" ]]; then
  echo "DEPENDENCY_HEADER_SCAN=fail"
  echo "canonical graph is not fresh"
  cat "$status_file"
  exit 1
fi

set +e
"$GRAPH_CLI" graph query --root "$ROOT_DIR" --profile default --format json --all --relation dependency --direction both --depth 0 >"$query_file"
query_exit=$?
set -e
if [[ "$query_exit" -ne 0 || "$(jq -r '.status // "invalid"' "$query_file" 2>/dev/null)" != "fresh" ]]; then
  echo "DEPENDENCY_HEADER_SCAN=fail"
  echo "canonical graph is not fresh"
  cat "$query_file"
  exit 1
fi

if [[ ${#INPUT_PATHS[@]} -gt 0 ]]; then
  printf '%s\n' "${INPUT_PATHS[@]}" | sort -u >"$selected_file"
elif [[ "$CHANGED" -eq 1 ]]; then
  {
    git -C "$ROOT_DIR" diff --name-only --diff-filter=ACMRT HEAD --
    git -C "$ROOT_DIR" ls-files --others --exclude-standard
  } | sed '/^$/d' | sort -u >"$selected_file"
fi

is_selected() {
  local path="$1"
  [[ ! -s "$selected_file" ]] || grep -Fqx -- "$path" "$selected_file"
}

is_checkable() {
  case "$1" in
    .git/*|.pytest_cache/*|.ruff_cache/*|reports/*|LICENSE|LICENSE.*|NOTICE|NOTICE.*|COPYING|COPYING.*) return 1 ;;
    *.bash|*.cfg|*.css|*.h|*.hpp|*.html|*.c|*.cc|*.cpp|*.md|*.py|*.rst|*.sh|*.toml|*.txt|*.yaml|*.yml|*.zsh) return 0 ;;
    *) return 1 ;;
  esac
}

missing=0
scanned=0
while IFS=$'\t' read -r path manifest_present owner; do
  [[ -n "$path" ]] || continue
  is_selected "$path" || continue
  is_checkable "$path" || continue
  scanned=$((scanned + 1))
  if [[ "$manifest_present" != "true" ]]; then
    echo "$path: missing dependency manifest"
    if [[ "$EXPLAIN_MISSING" -eq 1 ]]; then
      printf 'DEPENDENCY_HEADER_MISSING path=%s owner=%s authority=source-snapshot\n' "$path" "${owner:-unresolved}"
    fi
    missing=$((missing + 1))
  fi
done < <(jq -r '.nodes[] | select(.layer == "source") | [.path, (.payload.manifest_present // false), (.payload.manifest_responsibility // "")] | @tsv' "$query_file")

echo "DEPENDENCY_HEADER_SCAN=pass scanned=$scanned missing=$missing"
if [[ "$FAIL_MISSING" -eq 1 && "$missing" -gt 0 ]]; then
  exit 1
fi
