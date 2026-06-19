#!/usr/bin/env bash
# @dependency-start
# contract tool
# responsibility Provides scan dependency headers agent workflow automation.
# upstream design ../../documents/dependency-manifest-design.md dependency manifest DSL design
# downstream implementation ./check_dependency_header_format.sh validates manifest syntax
# downstream implementation ./check_dependency_graph.sh consumes manifest edges
# @dependency-end
set -euo pipefail

ROOT_DIR="$(git -C "$PWD" rev-parse --show-toplevel 2>/dev/null || pwd)"
FAIL_MISSING=0
CHANGED=0
EXPLAIN_MISSING=0
ALLOW_FRONTMATTER=0
HEADER_SCAN_LINES="${DEPENDENCY_HEADER_SCAN_LINES:-80}"
MISSING_PREVIEW_LINES="${DEPENDENCY_MISSING_PREVIEW_LINES:-20}"
declare -a INPUT_PATHS=()

usage() {
  cat <<'EOF'
Usage:
  scan_dependency_headers.sh [--root DIR] [--changed] [--fail-missing] [--allow-frontmatter] [--explain-missing] [paths...]

Scans checkable text files for @dependency-start / @dependency-end manifest markers.
Without --fail-missing this is report-only and exits 0.
--allow-frontmatter is accepted for policy-explicit callers; frontmatter is allowed by default.
--explain-missing prints a short first-lines preview and owner classification for missing manifests.
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
    --allow-frontmatter)
      ALLOW_FRONTMATTER=1
      shift
      ;;
    --explain-missing)
      EXPLAIN_MISSING=1
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
    .git/*|.pytest_cache/*|.ruff_cache/*|reports/*|LICENSE|LICENSE.*|NOTICE|NOTICE.*|COPYING|COPYING.*|vendor/agent-canon/LICENSE|vendor/agent-canon/LICENSE.*|vendor/agent-canon/NOTICE|vendor/agent-canon/NOTICE.*|vendor/agent-canon/COPYING|vendor/agent-canon/COPYING.*)
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

has_manifest_marker() {
  local path="$1"
  local marker="$2"
  awk -v max_lines="$HEADER_SCAN_LINES" -v marker="$marker" '
    NR > max_lines { exit 1 }
    index($0, marker) { found = 1; exit 0 }
    END {
      if (!found) {
        exit 1
      }
    }
  ' "$path"
}

has_manifest_markers() {
  local path="$1"
  has_manifest_marker "$path" '@dependency-start' &&
    has_manifest_marker "$path" '@dependency-end'
}

display_path() {
  local raw="$1"
  raw="${raw#./}"
  if [[ "$raw" = /* ]]; then
    case "$raw" in
      "$ROOT_DIR"/*) printf '%s\n' "${raw#$ROOT_DIR/}" ;;
      *) realpath -m --relative-to="$ROOT_DIR" "$raw" ;;
    esac
    return
  fi
  printf '%s\n' "$raw"
}

to_repo_path() {
  local raw="$1"
  raw="${raw#./}"
  if [[ "$raw" = /* ]]; then
    case "$raw" in
      "$ROOT_DIR"/*) printf '%s\n' "${raw#$ROOT_DIR/}" ;;
      *) realpath -m --relative-to="$ROOT_DIR" "$raw" ;;
    esac
    return
  fi
  printf '%s\n' "$raw"
}

real_source_path() {
  realpath -m --relative-to="$ROOT_DIR" "$1"
}

path_owner() {
  local path="$1"
  case "$path" in
    vendor/agent-canon/*)
      printf '%s\n' "submodule_source"
      return
      ;;
    .github/workflows/agent-coordination.yml|.github/PULL_REQUEST_TEMPLATE/agent_canon.md)
      printf '%s\n' "root_view"
      return
      ;;
  esac
  if [[ -L "$path" ]]; then
    printf '%s\n' "symlink"
    return
  fi
  printf '%s\n' "product_file"
}

missing_reason() {
  local path="$1"
  local has_start=0
  local has_end=0
  if has_manifest_marker "$path" '@dependency-start'; then
    has_start=1
  fi
  if has_manifest_marker "$path" '@dependency-end'; then
    has_end=1
  fi
  if [[ "$has_start" -eq 0 && "$has_end" -eq 0 ]]; then
    printf '%s\n' "missing_start_and_end_markers_in_first_${HEADER_SCAN_LINES}_lines"
  elif [[ "$has_start" -eq 0 ]]; then
    printf '%s\n' "missing_start_marker_in_first_${HEADER_SCAN_LINES}_lines"
  else
    printf '%s\n' "missing_end_marker_in_first_${HEADER_SCAN_LINES}_lines"
  fi
}

print_missing_explanation() {
  local path="$1"
  local shown
  shown="$(display_path "$path")"
  echo "MISSING_DEPENDENCY_EXPLANATION_BEGIN=$shown"
  echo "MISSING_DEPENDENCY_REASON=$shown $(missing_reason "$path")"
  echo "MISSING_DEPENDENCY_PREVIEW_LINES=$shown count=$MISSING_PREVIEW_LINES"
  sed -n "1,${MISSING_PREVIEW_LINES}p" "$path" | nl -ba -w1 -s ':'
  echo "MISSING_DEPENDENCY_EXPLANATION_END=$shown"
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
missing_product_file=0
missing_root_view=0
missing_symlink=0
missing_submodule_source=0
missing_other=0

while IFS= read -r raw_path; do
  [[ -n "$raw_path" ]] || continue
  path="$(to_repo_path "$raw_path")"
  [[ -f "$path" && ! -L "$path" ]] || { skipped=$((skipped + 1)); continue; }
  is_skip_path "$path" && { skipped=$((skipped + 1)); continue; }
  is_checkable_suffix "$path" || { skipped=$((skipped + 1)); continue; }
  is_binary_file "$path" || { skipped=$((skipped + 1)); continue; }
  checked=$((checked + 1))
  if ! has_manifest_markers "$path"; then
    owner="$(path_owner "$path")"
    case "$owner" in
      product_file) missing_product_file=$((missing_product_file + 1)) ;;
      root_view) missing_root_view=$((missing_root_view + 1)) ;;
      symlink) missing_symlink=$((missing_symlink + 1)) ;;
      submodule_source) missing_submodule_source=$((missing_submodule_source + 1)) ;;
      *) missing_other=$((missing_other + 1)) ;;
    esac
    echo "MISSING_DEPENDENCY_MANIFEST=$(display_path "$path") owner=$owner realpath=$(real_source_path "$path") reason=$(missing_reason "$path")"
    if [[ "$EXPLAIN_MISSING" -eq 1 ]]; then
      print_missing_explanation "$path"
    fi
    missing=$((missing + 1))
  fi
done < <(collect_paths)

echo "DEPENDENCY_HEADER_SCAN_CHECKED=$checked"
echo "DEPENDENCY_HEADER_SCAN_SKIPPED=$skipped"
echo "DEPENDENCY_HEADER_SCAN_MISSING=$missing"
echo "DEPENDENCY_HEADER_SCAN_MISSING_BY_OWNER product_file=$missing_product_file root_view=$missing_root_view symlink=$missing_symlink submodule_source=$missing_submodule_source other=$missing_other"

if [[ "$missing" -gt 0 && "$FAIL_MISSING" -eq 1 ]]; then
  echo "DEPENDENCY_HEADER_SCAN=fail"
  exit 1
fi

echo "DEPENDENCY_HEADER_SCAN=pass"
