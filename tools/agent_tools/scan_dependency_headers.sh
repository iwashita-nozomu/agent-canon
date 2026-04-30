#!/usr/bin/env bash
# @dependency-start
# responsibility Provides scan dependency headers agent workflow automation.
# upstream design ../../documents/dependency-manifest-design.md dependency manifest DSL design
# downstream implementation ./check_dependency_header_format.sh validates manifest syntax
# downstream implementation ./check_dependency_graph.sh consumes manifest edges
# @dependency-end
set -euo pipefail

ROOT_DIR="$(git -C "$(dirname "${BASH_SOURCE[0]}")" rev-parse --show-toplevel 2>/dev/null || pwd)"
FAIL_MISSING=0
CHANGED=0
HEADER_SCAN_LINES="${DEPENDENCY_HEADER_SCAN_LINES:-80}"
declare -a INPUT_PATHS=()

usage() {
  cat <<'EOF'
Usage:
  scan_dependency_headers.sh [--root DIR] [--changed] [--fail-missing] [paths...]

Scans checkable text files for @dependency-start / @dependency-end manifest markers.
Without --fail-missing this is report-only and exits 0.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --root)
      ROOT_DIR="$2"
      shift 2
      ;;
    --changed)
      CHANGED=1
      shift
      ;;
    --fail-missing)
      FAIL_MISSING=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      INPUT_PATHS+=("$1")
      shift
      ;;
  esac
done

cd "$ROOT_DIR"

is_checkable_suffix() {
  case "$1" in
    *.bash|*.cfg|*.css|*.h|*.hpp|*.html|*.c|*.cc|*.cpp|*.md|*.py|*.rst|*.sh|*.toml|*.txt|*.yaml|*.yml|*.zsh)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

is_skip_path() {
  case "$1" in
    .git/*|.pytest_cache/*|.ruff_cache/*|reports/agents/*)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

is_binary_file() {
  LC_ALL=C grep -Iq . "$1" 2>/dev/null
}

has_manifest_markers() {
  local path="$1"
  head -n "$HEADER_SCAN_LINES" "$path" | grep -q '@dependency-start' &&
    head -n "$HEADER_SCAN_LINES" "$path" | grep -q '@dependency-end'
}

display_path() {
  realpath -m --relative-to="$ROOT_DIR" "$1"
}

collect_paths() {
  if [[ ${#INPUT_PATHS[@]} -gt 0 ]]; then
    printf '%s\n' "${INPUT_PATHS[@]}"
    return
  fi
  if [[ "$CHANGED" -eq 1 ]]; then
    {
      git diff --name-only --diff-filter=ACMRT HEAD -- 2>/dev/null || true
      git ls-files --others --exclude-standard 2>/dev/null || true
    } | awk 'NF'
    return
  fi
  git ls-files
}

missing=0
checked=0
skipped=0

while IFS= read -r raw_path; do
  [[ -n "$raw_path" ]] || continue
  path="${raw_path#./}"
  if [[ "$path" = /* ]]; then
    path="$(realpath -m --relative-to="$ROOT_DIR" "$path")"
  fi
  [[ -f "$path" && ! -L "$path" ]] || { skipped=$((skipped + 1)); continue; }
  is_skip_path "$path" && { skipped=$((skipped + 1)); continue; }
  is_checkable_suffix "$path" || { skipped=$((skipped + 1)); continue; }
  is_binary_file "$path" || { skipped=$((skipped + 1)); continue; }
  checked=$((checked + 1))
  if ! has_manifest_markers "$path"; then
    echo "MISSING_DEPENDENCY_MANIFEST=$(display_path "$path")"
    missing=$((missing + 1))
  fi
done < <(collect_paths)

echo "DEPENDENCY_HEADER_SCAN_CHECKED=$checked"
echo "DEPENDENCY_HEADER_SCAN_SKIPPED=$skipped"
echo "DEPENDENCY_HEADER_SCAN_MISSING=$missing"

if [[ "$missing" -gt 0 && "$FAIL_MISSING" -eq 1 ]]; then
  echo "DEPENDENCY_HEADER_SCAN=fail"
  exit 1
fi

echo "DEPENDENCY_HEADER_SCAN=pass"
