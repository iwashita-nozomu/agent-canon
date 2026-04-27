#!/usr/bin/env bash
# @dependency-start
# upstream design ../../documents/dependency-manifest-design.md dependency manifest DSL design
# upstream implementation ./scan_dependency_headers.sh finds files with manifests
# downstream implementation ./check_dependency_graph.sh consumes validated manifest lines
# @dependency-end
set -euo pipefail

ROOT_DIR="$(git -C "$(dirname "${BASH_SOURCE[0]}")" rev-parse --show-toplevel 2>/dev/null || pwd)"
REQUIRE_HEADER=0
CHANGED=0
HEADER_SCAN_LINES="${DEPENDENCY_HEADER_SCAN_LINES:-80}"
declare -a INPUT_PATHS=()

usage() {
  cat <<'EOF'
Usage:
  check_dependency_header_format.sh [--root DIR] [--changed] [--require-header] [paths...]

Validates @dependency-start / @dependency-end manifest syntax.
Files without a manifest are skipped unless --require-header is set.
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
    --require-header)
      REQUIRE_HEADER=1
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

strip_manifest_line() {
  local line="$1"
  line="${line%$'\r'}"
  line="${line#"${line%%[![:space:]]*}"}"
  case "$line" in
    "# "*) line="${line#\# }" ;;
    "#"*) line="${line#\#}" ;;
  esac
  case "$line" in
    "// "*) line="${line#// }" ;;
    "//"*) line="${line#//}" ;;
  esac
  case "$line" in
    "* "*) line="${line#\* }" ;;
    "*"*) line="${line#\*}" ;;
  esac
  line="${line#"${line%%[![:space:]]*}"}"
  line="${line%"${line##*[![:space:]]}"}"
  line="${line%,}"
  line="${line#"${line%%[![:space:]]*}"}"
  line="${line%"${line##*[![:space:]]}"}"
  if [[ "$line" == \"*\" ]]; then
    line="${line#\"}"
    line="${line%\"}"
  fi
  printf '%s\n' "$line"
}

normalize_path() {
  local source_file="$1"
  local rel_path="$2"
  local source_dir
  source_dir="$(dirname "$source_file")"
  realpath -m --relative-to="$ROOT_DIR" "$source_dir/$rel_path"
}

check_file() {
  local file="$1"
  local start_count end_count start_line end_line line_no line stripped
  local direction kind rel_path reason target
  [[ -f "$file" && ! -L "$file" ]] || return 0

  start_count=0
  end_count=0
  start_line=0
  end_line=0
  line_no=0
  while IFS= read -r line && [[ "$line_no" -lt "$HEADER_SCAN_LINES" ]]; do
    line_no=$((line_no + 1))
    stripped="$(strip_manifest_line "$line")"
    if [[ "$stripped" == "@dependency-start" ]]; then
      if [[ "$start_line" -ne 0 && "$end_line" -eq 0 ]]; then
        echo "$file: duplicate @dependency-start before @dependency-end"
        return 1
      fi
      [[ "$end_line" -ne 0 ]] && break
      start_count=$((start_count + 1))
      start_line="$line_no"
    elif [[ "$stripped" == "@dependency-end" ]]; then
      [[ "$start_line" -eq 0 ]] && {
        echo "$file: @dependency-end appears before @dependency-start"
        return 1
      }
      end_count=$((end_count + 1))
      end_line="$line_no"
      break
    fi
  done < "$file"

  if [[ "$start_count" -eq 0 && "$end_count" -eq 0 ]]; then
    is_checkable_suffix "$file" || return 0
    if [[ "$REQUIRE_HEADER" -eq 1 ]]; then
      echo "$file: missing dependency manifest markers"
      return 1
    fi
    return 0
  fi
  if [[ "$start_count" -ne 1 || "$end_count" -ne 1 ]]; then
    echo "$file: expected one top dependency manifest block"
    return 1
  fi
  if [[ "$start_line" -ge "$end_line" ]]; then
    echo "$file: @dependency-start must appear before @dependency-end"
    return 1
  fi

  line_no=0
  while IFS= read -r line; do
    line_no=$((line_no + 1))
    [[ "$line_no" -gt "$start_line" && "$line_no" -lt "$end_line" ]] || continue
    stripped="$(strip_manifest_line "$line")"
    case "$stripped" in
      ""|"/*"|"*/"|"<!--"|"-->"|'"""'|"'''" )
        continue
        ;;
    esac
    read -r direction kind rel_path reason <<< "$stripped"
    if [[ -z "${direction:-}" || -z "${kind:-}" || -z "${rel_path:-}" || -z "${reason:-}" ]]; then
      echo "$file:$line_no: dependency line must be: direction kind relative-path reason"
      return 1
    fi
    if [[ "$direction" != "upstream" && "$direction" != "downstream" ]]; then
      echo "$file:$line_no: invalid direction '$direction'"
      return 1
    fi
    if [[ "$kind" != "design" && "$kind" != "implementation" && "$kind" != "environment" ]]; then
      echo "$file:$line_no: invalid kind '$kind'"
      return 1
    fi
    if [[ "$rel_path" = /* || "$rel_path" == *"://"* ]]; then
      echo "$file:$line_no: dependency path must be relative: $rel_path"
      return 1
    fi
    target="$(normalize_path "$file" "$rel_path")"
    if [[ ! -e "$target" ]]; then
      echo "$file:$line_no: dependency target does not exist: $rel_path"
      return 1
    fi
  done < "$file"
}

failures=0
while IFS= read -r raw_path; do
  [[ -n "$raw_path" ]] || continue
  path="${raw_path#./}"
  if ! check_file "$path"; then
    failures=$((failures + 1))
  fi
done < <(collect_paths)

if [[ "$failures" -gt 0 ]]; then
  echo "DEPENDENCY_HEADER_FORMAT=fail"
  exit 1
fi

echo "DEPENDENCY_HEADER_FORMAT=pass"
