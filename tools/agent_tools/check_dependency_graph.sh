#!/usr/bin/env bash
# @dependency-start
# responsibility Builds and validates dependency manifest graph semantics.
# upstream design ../../documents/dependency-manifest-design.md dependency graph semantics
# upstream implementation ./check_dependency_header_format.sh validates source manifests
# downstream implementation ../../tests/agent_tools/test_dependency_manifest_tools.py verifies graph behavior
# @dependency-end
set -euo pipefail

ROOT_DIR="$(git -C "$(dirname "${BASH_SOURCE[0]}")" rev-parse --show-toplevel 2>/dev/null || pwd)"
PRINT_EDGES=0
CHANGED=0
CHECK_BIDIRECTIONAL=0
HEADER_SCAN_LINES="${DEPENDENCY_HEADER_SCAN_LINES:-80}"
declare -a INPUT_PATHS=()

usage() {
  cat <<'EOF'
Usage:
  check_dependency_graph.sh [--root DIR] [--changed] [--print-edges] [--check-bidirectional] [paths...]

Builds separate upstream/downstream dependency graphs and validates:
  - isolated manifest files with no graph edge
  - self references
  - cycles in upstream and downstream graphs

With --check-bidirectional it also validates:
  - bidirectional consistency
  - reverse-edge kind matches
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
    --print-edges)
      PRINT_EDGES=1
      shift
      ;;
    --check-bidirectional)
      CHECK_BIDIRECTIONAL=1
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

extract_edges() {
  local file="$1"
  local start_line=0 end_line=0 line_no=0 line stripped direction kind rel_path reason source target
  [[ -f "$file" && ! -L "$file" ]] || return 0
  while IFS= read -r line && [[ "$line_no" -lt "$HEADER_SCAN_LINES" ]]; do
    line_no=$((line_no + 1))
    stripped="$(strip_manifest_line "$line")"
    if [[ "$stripped" == "@dependency-start" && "$start_line" -eq 0 ]]; then
      start_line="$line_no"
    elif [[ "$stripped" == "@dependency-end" && "$start_line" -gt 0 ]]; then
      end_line="$line_no"
      break
    fi
  done < "$file"
  [[ "$start_line" -gt 0 && "$end_line" -gt "$start_line" ]] || return 0

  source="$(realpath -m --relative-to="$ROOT_DIR" "$file")"
  printf '%s\n' "$source" >> "$manifest_files"
  line_no=0
  while IFS= read -r line; do
    line_no=$((line_no + 1))
    [[ "$line_no" -gt "$start_line" && "$line_no" -lt "$end_line" ]] || continue
    stripped="$(strip_manifest_line "$line")"
    [[ -n "$stripped" ]] || continue
    case "$stripped" in
      "/*"|"*/"|"<!--"|"-->"|'"""'|"'''" ) continue ;;
    esac
    [[ "$stripped" == responsibility[[:space:]]* ]] && continue
    read -r direction kind rel_path reason <<< "$stripped"
    [[ "$direction" == "upstream" || "$direction" == "downstream" ]] || continue
    target="$(normalize_path "$file" "$rel_path")"
    printf '%s\t%s\t%s\t%s\n' "$direction" "$kind" "$source" "$target"
  done < "$file"
}

edges_file="$(mktemp)"
manifest_files="$(mktemp)"
trap 'rm -f "$edges_file" "$edges_file.sorted" "$manifest_files" "$manifest_files.sorted"' EXIT

while IFS= read -r raw_path; do
  [[ -n "$raw_path" ]] || continue
  path="${raw_path#./}"
  extract_edges "$path" >> "$edges_file"
done < <(collect_paths)

sort -u "$edges_file" > "$edges_file.sorted"
mv "$edges_file.sorted" "$edges_file"
sort -u "$manifest_files" > "$manifest_files.sorted"
mv "$manifest_files.sorted" "$manifest_files"

if [[ "$PRINT_EDGES" -eq 1 ]]; then
  cat "$edges_file"
fi

failures=0

while IFS= read -r manifest_file; do
  [[ -n "$manifest_file" ]] || continue
  if ! awk -F '\t' -v file="$manifest_file" \
    '$3 == file || $4 == file { found = 1 } END { exit(found ? 0 : 1) }' "$edges_file"; then
    echo "$manifest_file: isolated dependency manifest has no graph edges"
    failures=$((failures + 1))
  fi
done < "$manifest_files"

while IFS=$'\t' read -r direction kind source target; do
  [[ -n "${direction:-}" ]] || continue
  if [[ "$source" == "$target" ]]; then
    echo "$source: self reference in $direction $kind edge"
    failures=$((failures + 1))
  fi
  if [[ "$CHECK_BIDIRECTIONAL" -eq 1 ]]; then
    if [[ "$direction" == "upstream" ]]; then
      reverse_direction="downstream"
    else
      reverse_direction="upstream"
    fi
    if ! awk -F '\t' -v d="$reverse_direction" -v k="$kind" -v s="$target" -v t="$source" \
      '$1 == d && $2 == k && $3 == s && $4 == t { found = 1 } END { exit(found ? 0 : 1) }' "$edges_file"; then
      echo "$source: missing reverse $reverse_direction $kind edge from $target"
      failures=$((failures + 1))
    fi
    if awk -F '\t' -v d="$reverse_direction" -v k="$kind" -v s="$target" -v t="$source" \
      '$1 == d && $2 != k && $3 == s && $4 == t { found = 1 } END { exit(found ? 0 : 1) }' "$edges_file"; then
      echo "$source: reverse edge from $target uses a different kind"
      failures=$((failures + 1))
    fi
  fi
done < "$edges_file"

check_cycles() {
  local direction="$1"
  awk -F '\t' -v wanted="$direction" '
    $1 == wanted {
      adj[$3] = adj[$3] SUBSEP $4
      nodes[$3] = 1
      nodes[$4] = 1
    }
    function dfs(node,    raw, parts, i, next_node) {
      state[node] = 1
      raw = adj[node]
      n = split(raw, parts, SUBSEP)
      for (i = 1; i <= n; i++) {
        next_node = parts[i]
        if (next_node == "") {
          continue
        }
        if (state[next_node] == 1) {
          print wanted " cycle includes " node " -> " next_node
          found = 1
          return
        }
        if (state[next_node] == 0) {
          dfs(next_node)
          if (found) {
            return
          }
        }
      }
      state[node] = 2
    }
    END {
      for (node in nodes) {
        if (state[node] == 0) {
          dfs(node)
          if (found) {
            exit 1
          }
        }
      }
    }
  ' "$edges_file"
}

if ! check_cycles upstream; then
  failures=$((failures + 1))
fi
if ! check_cycles downstream; then
  failures=$((failures + 1))
fi

if [[ "$failures" -gt 0 ]]; then
  echo "DEPENDENCY_GRAPH=fail"
  exit 1
fi

echo "DEPENDENCY_GRAPH=pass"
