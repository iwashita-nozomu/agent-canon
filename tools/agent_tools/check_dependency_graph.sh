#!/usr/bin/env bash
# @dependency-start
# contract tool
# responsibility Builds and validates dependency manifest graph semantics.
# upstream design ../../documents/dependency-manifest-design.md dependency graph semantics
# upstream design ../../documents/dependency-contract-kinds.toml registered dependency header contract kinds
# upstream implementation ./check_dependency_header_format.sh validates source manifests
# downstream implementation ../../tests/agent_tools/test_dependency_manifest_tools.py verifies graph behavior
# @dependency-end
set -euo pipefail

ROOT_DIR="$(git -C "$PWD" rev-parse --show-toplevel 2>/dev/null || pwd)"
PRINT_EDGES=0
CHANGED=0
CHECK_BIDIRECTIONAL=0
CYCLE_REPORT_ONLY=0
ALLOW_FRONTMATTER=0
LIST_RELATED=0
FOCUS_CHANGED=0
EDIT_SCOPE=0
EDIT_SCOPE_CHANGED=0
GRAPH_TSV_OUTPUT=""
EDIT_SCOPE_HITS_FILE=""
HEADER_SCAN_LINES="${DEPENDENCY_HEADER_SCAN_LINES:-80}"
declare -a INPUT_PATHS=()
declare -a FOCUS_PATHS=()
declare -a EDIT_SCOPE_PATHS=()

usage() {
  cat <<'EOF'
Usage:
  check_dependency_graph.sh [--root DIR] [--changed] [--print-edges] [--graph-tsv PATH] [--list-related] [--focus PATH] [--focus-changed] [--edit-scope PATH] [--edit-scope-changed] [--search-hits-file PATH] [--check-bidirectional] [--cycle-report-only] [--allow-frontmatter] [paths...]

Builds separate upstream/downstream dependency graphs and validates:
  - isolated manifest files with no graph edge
  - self references
  - cycles in upstream and downstream graphs

With --check-bidirectional it also validates:
  - bidirectional consistency
  - reverse-edge kind matches

With --cycle-report-only it reports upstream/downstream cycles without failing.
Use this for repo-wide migration or PR gates that also publish a graph report.

With --list-related it prints every manifest edge declared by, or pointing at,
the focused path set. Use --focus PATH for explicit paths or --focus-changed
to list the dependency surfaces for current changed files.

With --graph-tsv it writes a stable machine-readable graph artifact with columns:
direction, kind, source, target.

With --edit-scope, --edit-scope-changed, or --search-hits-file it expands files
found by a repo-wide text search into edit-scope candidates using the manifest
graph. Search hit files themselves, declared dependencies, incoming dependents,
and directory-contained dependency surfaces are emitted as
DEPENDENCY_EDIT_SCOPE_PATH lines.
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
    --graph-tsv)
      GRAPH_TSV_OUTPUT="$2"
      shift 2
      ;;
    --list-related)
      LIST_RELATED=1
      shift
      ;;
    --focus)
      FOCUS_PATHS+=("$2")
      shift 2
      ;;
    --focus-changed)
      FOCUS_CHANGED=1
      shift
      ;;
    --edit-scope)
      EDIT_SCOPE=1
      EDIT_SCOPE_PATHS+=("$2")
      shift 2
      ;;
    --edit-scope-changed)
      EDIT_SCOPE_CHANGED=1
      shift
      ;;
    --search-hits-file)
      EDIT_SCOPE=1
      EDIT_SCOPE_HITS_FILE="$2"
      shift 2
      ;;
    --check-bidirectional)
      CHECK_BIDIRECTIONAL=1
      shift
      ;;
    --cycle-report-only)
      CYCLE_REPORT_ONLY=1
      shift
      ;;
    --allow-frontmatter)
      ALLOW_FRONTMATTER=1
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

ROOT_DIR="$(realpath -m "$ROOT_DIR")"
cd "$ROOT_DIR"

collect_paths() {
  if [[ ${#INPUT_PATHS[@]} -gt 0 ]]; then
    printf '%s\n' "${INPUT_PATHS[@]}"
    return
  fi
  if [[ "$CHANGED" -eq 1 ]]; then
    collect_changed_paths
    return
  fi
  git ls-files
}

collect_changed_paths() {
  {
    git diff --name-only --diff-filter=ACMRT HEAD -- 2>/dev/null || true
    git ls-files --others --exclude-standard 2>/dev/null || true
  } | awk 'NF'
}

collect_focus_paths() {
  if [[ ${#FOCUS_PATHS[@]} -gt 0 ]]; then
    printf '%s\n' "${FOCUS_PATHS[@]}"
    return
  fi
  if [[ "$FOCUS_CHANGED" -eq 1 ]]; then
    collect_changed_paths
  fi
}

path_from_search_hit_line() {
  local raw_line="$1"
  local candidate
  raw_line="${raw_line#./}"
  if [[ -e "$ROOT_DIR/$raw_line" || -L "$ROOT_DIR/$raw_line" ]]; then
    printf '%s\n' "$raw_line"
    return
  fi
  candidate="${raw_line%%:*}"
  if [[ "$candidate" != "$raw_line" && ( -e "$ROOT_DIR/$candidate" || -L "$ROOT_DIR/$candidate" ) ]]; then
    printf '%s\n' "$candidate"
    return
  fi
  printf '%s\n' "$raw_line"
}

collect_edit_scope_paths() {
  if [[ ${#EDIT_SCOPE_PATHS[@]} -gt 0 ]]; then
    printf '%s\n' "${EDIT_SCOPE_PATHS[@]}"
  fi
  if [[ "$EDIT_SCOPE_CHANGED" -eq 1 ]]; then
    collect_changed_paths
  fi
  if [[ -n "$EDIT_SCOPE_HITS_FILE" ]]; then
    while IFS= read -r raw_hit; do
      [[ -n "$raw_hit" ]] || continue
      path_from_search_hit_line "$raw_hit"
    done < "$EDIT_SCOPE_HITS_FILE"
  fi
}

normalize_input_path() {
  local raw_path="$1"
  if [[ "$raw_path" = /* ]]; then
    realpath -m --relative-to="$ROOT_DIR" "$raw_path"
  else
    realpath -m --relative-to="$ROOT_DIR" "$ROOT_DIR/$raw_path"
  fi
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
  local source_context
  local source_dir
  source_context="$(source_context_file "$source_file")"
  source_dir="$(dirname "$source_context")"
  realpath -m --relative-to="$ROOT_DIR" "$source_dir/$rel_path"
}

source_context_file() {
  local source_file="$1"
  case "$source_file" in
    .github/workflows/agent-coordination.yml|.github/PULL_REQUEST_TEMPLATE/agent_canon.md)
      if [[ -f "vendor/agent-canon/$source_file" ]]; then
        printf 'vendor/agent-canon/%s\n' "$source_file"
        return
      fi
      ;;
    .github/scripts/checkout_agent_canon_submodule.sh)
      if [[ -f "vendor/agent-canon/tools/ci/checkout_agent_canon_submodule.sh" ]]; then
        printf '%s\n' "vendor/agent-canon/tools/ci/checkout_agent_canon_submodule.sh"
        return
      fi
      ;;
  esac
  printf '%s\n' "$source_file"
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
    [[ "$stripped" == contract[[:space:]]* ]] && continue
    read -r direction kind rel_path reason <<< "$stripped"
    [[ "$direction" == "upstream" || "$direction" == "downstream" ]] || continue
    target="$(normalize_path "$file" "$rel_path")"
    printf '%s\t%s\t%s\t%s\n' "$direction" "$kind" "$source" "$target"
  done < "$file"
}

edges_file="$(mktemp)"
manifest_files="$(mktemp)"
edit_scope_file="$(mktemp)"
trap 'rm -f "$edges_file" "$edges_file.sorted" "$manifest_files" "$manifest_files.sorted" "$edit_scope_file"' EXIT

while IFS= read -r raw_path; do
  [[ -n "$raw_path" ]] || continue
  path="$(normalize_input_path "$raw_path")"
  extract_edges "$path" >> "$edges_file"
done < <(collect_paths)

sort -u "$edges_file" > "$edges_file.sorted"
mv "$edges_file.sorted" "$edges_file"
sort -u "$manifest_files" > "$manifest_files.sorted"
mv "$manifest_files.sorted" "$manifest_files"

if [[ "$PRINT_EDGES" -eq 1 ]]; then
  cat "$edges_file"
fi

if [[ -n "$GRAPH_TSV_OUTPUT" ]]; then
  mkdir -p "$(dirname "$GRAPH_TSV_OUTPUT")"
  {
    printf 'direction\tkind\tsource\ttarget\n'
    cat "$edges_file"
  } > "$GRAPH_TSV_OUTPUT"
  echo "DEPENDENCY_GRAPH_TSV=$GRAPH_TSV_OUTPUT"
fi

if [[ "$LIST_RELATED" -eq 1 ]]; then
  related_count=0
  while IFS= read -r raw_focus; do
    [[ -n "$raw_focus" ]] || continue
    focus="$(normalize_input_path "$raw_focus")"
    related_count=$((related_count + 1))
    echo "DEPENDENCY_RELATED_SURFACE=$focus"
    awk -F '\t' -v file="$focus" '
      $3 == file {
        printf "DEPENDENCY_RELATED_EDGE role=declared_%s kind=%s source=%s target=%s\n", $1, $2, $3, $4
        found = 1
      }
      $4 == file {
        printf "DEPENDENCY_RELATED_EDGE role=incoming_%s kind=%s source=%s target=%s\n", $1, $2, $3, $4
        found = 1
      }
      END {
        if (!found) {
          printf "DEPENDENCY_RELATED_EDGE role=none path=%s\n", file
        }
      }
    ' "$edges_file"
  done < <(collect_focus_paths | sort -u)
  echo "DEPENDENCY_RELATED_SURFACES=$related_count"
fi

emit_edit_scope_for_focus() {
  local focus="$1"
  local focus_dir=""
  if [[ -d "$ROOT_DIR/$focus" ]]; then
    focus_dir="$focus"
  else
    focus_dir="$(dirname "$focus")"
  fi
  printf 'DEPENDENCY_EDIT_SCOPE_PATH role=search_hit path=%s\n' "$focus"
  awk -F '\t' -v file="$focus" -v dir="$focus_dir" '
    $3 == file {
      printf "DEPENDENCY_EDIT_SCOPE_PATH role=declared_%s kind=%s path=%s source=%s target=%s\n", $1, $2, $4, $3, $4
    }
    $4 == file {
      printf "DEPENDENCY_EDIT_SCOPE_PATH role=incoming_%s kind=%s path=%s source=%s target=%s\n", $1, $2, $3, $3, $4
    }
    dir != "." && ($3 == dir || index($3, dir "/") == 1 || $4 == dir || index($4, dir "/") == 1) {
      printf "DEPENDENCY_EDIT_SCOPE_PATH role=directory_related_%s kind=%s path=%s source=%s target=%s\n", $1, $2, ($3 == file ? $4 : $3), $3, $4
    }
  ' "$edges_file"
}

if [[ "$EDIT_SCOPE" -eq 1 || "$EDIT_SCOPE_CHANGED" -eq 1 ]]; then
  while IFS= read -r raw_scope_path; do
    [[ -n "$raw_scope_path" ]] || continue
    scope_path="$(normalize_input_path "$raw_scope_path")"
    emit_edit_scope_for_focus "$scope_path"
  done < <(collect_edit_scope_paths | sort -u) | sort -u > "$edit_scope_file"
  cat "$edit_scope_file"
  echo "DEPENDENCY_EDIT_SCOPE_PATHS=$(wc -l < "$edit_scope_file" | tr -d ' ')"
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
  if [[ "$CYCLE_REPORT_ONLY" -eq 1 ]]; then
    echo "DEPENDENCY_GRAPH_UPSTREAM_CYCLES=report_only"
  else
    failures=$((failures + 1))
  fi
fi
if ! check_cycles downstream; then
  if [[ "$CYCLE_REPORT_ONLY" -eq 1 ]]; then
    echo "DEPENDENCY_GRAPH_DOWNSTREAM_CYCLES=report_only"
  else
    failures=$((failures + 1))
  fi
fi

if [[ "$failures" -gt 0 ]]; then
  echo "DEPENDENCY_GRAPH=fail"
  exit 1
fi

echo "DEPENDENCY_GRAPH=pass"
