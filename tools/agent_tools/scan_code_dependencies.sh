#!/usr/bin/env bash
# @dependency-start
# responsibility Extracts source-code dependency edges independently from manifest headers.
# upstream design ../../agents/workflows/hypothesis-validation-workflow.md analysis-first workflow contract
# downstream implementation ../../tests/agent_tools/test_dependency_manifest_tools.py verifies scanner behavior
# downstream design ../../tools/README.md documents agent tool inventory
# @dependency-end
set -euo pipefail

ROOT_DIR="$(git -C "$(dirname "${BASH_SOURCE[0]}")" rev-parse --show-toplevel 2>/dev/null || pwd)"
CHANGED=0
PRINT_UNRESOLVED=0
declare -a INPUT_PATHS=()

usage() {
  cat <<'EOF'
Usage:
  scan_code_dependencies.sh [--root DIR] [--changed] [--print-unresolved] [paths...]

Extracts best-effort code dependency edges from source files.
This is intentionally separate from dependency manifest header tools:
  - Python: import / from import
  - C/C++: local #include "..."
  - shell: source / . relative-file

Output columns:
  CODE_DEPENDENCY<TAB>language<TAB>kind<TAB>source<TAB>target<TAB>symbol<TAB>raw
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
    --print-unresolved)
      PRINT_UNRESOLVED=1
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

trim() {
  local value="$1"
  value="${value#"${value%%[![:space:]]*}"}"
  value="${value%"${value##*[![:space:]]}"}"
  printf '%s' "$value"
}

relative_path() {
  realpath -m --relative-to="$ROOT_DIR" "$1"
}

emit_edge() {
  local language="$1"
  local kind="$2"
  local source="$3"
  local target="$4"
  local symbol="$5"
  local raw="$6"
  if [[ -z "$target" && "$PRINT_UNRESOLVED" -eq 0 ]]; then
    return
  fi
  printf 'CODE_DEPENDENCY\t%s\t%s\t%s\t%s\t%s\t%s\n' \
    "$language" "$kind" "$source" "$target" "$symbol" "$raw"
}

resolve_python_module() {
  local source_file="$1"
  local module="$2"
  local source_dir module_path dots rest base
  source_dir="$(dirname "$source_file")"
  module="$(trim "$module")"
  [[ -n "$module" ]] || return 1

  if [[ "$module" == .* ]]; then
    dots="${module%%[!.]*}"
    rest="${module#"$dots"}"
    base="$source_dir"
    for ((i = 1; i < ${#dots}; i++)); do
      base="$(dirname "$base")"
    done
    if [[ -n "$rest" ]]; then
      module_path="$base/${rest//./\/}"
    else
      module_path="$base"
    fi
  else
    module_path="${module//./\/}"
  fi

  if [[ -f "$module_path.py" ]]; then
    relative_path "$module_path.py"
    return 0
  fi
  if [[ -f "$module_path/__init__.py" ]]; then
    relative_path "$module_path/__init__.py"
    return 0
  fi
  return 1
}

scan_python() {
  local file="$1"
  local source raw line module imports import_item target combined_module
  source="$(relative_path "$file")"
  while IFS= read -r raw; do
    line="${raw%%#*}"
    line="$(trim "$line")"
    [[ -n "$line" ]] || continue
    if [[ "$line" =~ ^from[[:space:]]+([^[:space:]]+)[[:space:]]+import[[:space:]]+(.+) ]]; then
      module="${BASH_REMATCH[1]}"
      imports="${BASH_REMATCH[2]}"
      target="$(resolve_python_module "$file" "$module" 2>/dev/null || true)"
      emit_edge "python" "import" "$source" "$target" "$module" "$raw"
      IFS=',' read -ra import_items <<< "$imports"
      for import_item in "${import_items[@]}"; do
        import_item="$(trim "${import_item%% as *}")"
        [[ -n "$import_item" && "$import_item" != "*" ]] || continue
        if [[ "$module" == .* && "$module" != *[!.] ]]; then
          combined_module="$module$import_item"
        else
          combined_module="$module.$import_item"
        fi
        target="$(resolve_python_module "$file" "$combined_module" 2>/dev/null || true)"
        emit_edge "python" "from-import-symbol" "$source" "$target" "$combined_module" "$raw"
      done
    elif [[ "$line" =~ ^import[[:space:]]+(.+) ]]; then
      imports="${BASH_REMATCH[1]}"
      IFS=',' read -ra import_items <<< "$imports"
      for import_item in "${import_items[@]}"; do
        module="$(trim "${import_item%% as *}")"
        [[ -n "$module" ]] || continue
        target="$(resolve_python_module "$file" "$module" 2>/dev/null || true)"
        emit_edge "python" "import" "$source" "$target" "$module" "$raw"
      done
    fi
  done < "$file"
}

scan_c_family() {
  local file="$1"
  local source raw include target source_dir
  source="$(relative_path "$file")"
  source_dir="$(dirname "$file")"
  while IFS= read -r raw; do
    if [[ "$raw" =~ ^[[:space:]]*#[[:space:]]*include[[:space:]]+\"([^\"]+)\" ]]; then
      include="${BASH_REMATCH[1]}"
      target=""
      if [[ -f "$source_dir/$include" ]]; then
        target="$(relative_path "$source_dir/$include")"
      elif [[ -f "$include" ]]; then
        target="$(relative_path "$include")"
      fi
      emit_edge "c-family" "include" "$source" "$target" "$include" "$raw"
    fi
  done < "$file"
}

scan_shell() {
  local file="$1"
  local source raw include target source_dir
  source="$(relative_path "$file")"
  source_dir="$(dirname "$file")"
  while IFS= read -r raw; do
    raw="${raw%%#*}"
    raw="$(trim "$raw")"
    [[ -n "$raw" ]] || continue
    if [[ "$raw" =~ ^(source|\.)[[:space:]]+([^[:space:];]+) ]]; then
      include="${BASH_REMATCH[2]}"
      include="${include%\"}"
      include="${include#\"}"
      target=""
      if [[ -f "$source_dir/$include" ]]; then
        target="$(relative_path "$source_dir/$include")"
      elif [[ -f "$include" ]]; then
        target="$(relative_path "$include")"
      fi
      emit_edge "shell" "source" "$source" "$target" "$include" "$raw"
    fi
  done < "$file"
}

count=0
while IFS= read -r raw_path; do
  [[ -n "$raw_path" ]] || continue
  path="${raw_path#./}"
  [[ -f "$path" && ! -L "$path" ]] || continue
  case "$path" in
    *.py)
      scan_python "$path"
      count=$((count + 1))
      ;;
    *.c|*.cc|*.cpp|*.h|*.hpp)
      scan_c_family "$path"
      count=$((count + 1))
      ;;
    *.sh|*.bash|*.zsh)
      scan_shell "$path"
      count=$((count + 1))
      ;;
  esac
done < <(collect_paths)

echo "CODE_DEPENDENCY_SCAN=pass files=$count"
