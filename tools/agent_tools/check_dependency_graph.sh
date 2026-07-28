#!/usr/bin/env bash
# @dependency-start
# contract tool
# responsibility Projects and validates dependency relations captured by the canonical graph.
# upstream design ../../documents/design/dependency-manifest-design.md dependency graph semantics
# upstream implementation ../../rust/agent-canon/src/graph.rs owns dependency parsing, binding, and storage
# downstream implementation ./render_dependency_manifest_graph.py renders exported dependency TSV
# @dependency-end
set -euo pipefail

ROOT_DIR="$(git -C "$PWD" rev-parse --show-toplevel 2>/dev/null || pwd)"
PRINT_EDGES=0
CHANGED=0
CHECK_BIDIRECTIONAL=0
CYCLE_REPORT_ONLY=0
LIST_RELATED=0
FOCUS_CHANGED=0
EDIT_SCOPE=0
EDIT_SCOPE_CHANGED=0
GRAPH_TSV_OUTPUT=""
EDIT_SCOPE_HITS_FILE=""
declare -a INPUT_PATHS=()
declare -a FOCUS_PATHS=()
declare -a EDIT_SCOPE_PATHS=()

usage() {
  cat <<'EOF'
Usage:
  check_dependency_graph.sh [--root DIR] [--changed] [--print-edges] [--graph-tsv PATH] [--list-related] [--focus PATH] [--focus-changed] [--edit-scope PATH] [--edit-scope-changed] [--search-hits-file PATH] [--check-bidirectional] [--cycle-report-only] [paths...]

Consumes one canonical graph query; it does not parse source manifests.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --root) ROOT_DIR="$2"; shift 2 ;;
    --changed) CHANGED=1; shift ;;
    --print-edges) PRINT_EDGES=1; shift ;;
    --graph-tsv) GRAPH_TSV_OUTPUT="$2"; shift 2 ;;
    --list-related) LIST_RELATED=1; shift ;;
    --focus) FOCUS_PATHS+=("${2#./}"); shift 2 ;;
    --focus-changed) FOCUS_CHANGED=1; shift ;;
    --edit-scope) EDIT_SCOPE=1; EDIT_SCOPE_PATHS+=("${2#./}"); shift 2 ;;
    --edit-scope-changed) EDIT_SCOPE=1; EDIT_SCOPE_CHANGED=1; shift ;;
    --search-hits-file) EDIT_SCOPE=1; EDIT_SCOPE_HITS_FILE="$2"; shift 2 ;;
    --check-bidirectional) CHECK_BIDIRECTIONAL=1; shift ;;
    --cycle-report-only) CYCLE_REPORT_ONLY=1; shift ;;
    --allow-frontmatter) shift ;;
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
all_edges="$(mktemp)"
edges_file="$(mktemp)"
manifest_files="$(mktemp)"
selected_file="$(mktemp)"
scope_file="$(mktemp)"
trap 'rm -f "$status_file" "$query_file" "$all_edges" "$edges_file" "$manifest_files" "$selected_file" "$scope_file"' EXIT

set +e
"$GRAPH_CLI" graph status --root "$ROOT_DIR" --profile default --format json >"$status_file"
status_exit=$?
set -e
if [[ "$status_exit" -ne 0 || "$(jq -r '.status // "invalid"' "$status_file" 2>/dev/null)" != "fresh" ]]; then
  echo "DEPENDENCY_GRAPH=fail"
  echo "canonical graph is not fresh"
  cat "$status_file"
  exit 1
fi

set +e
"$GRAPH_CLI" graph query --root "$ROOT_DIR" --profile default --format json --all --relation all --direction both --depth 0 >"$query_file"
query_exit=$?
set -e
if [[ "$query_exit" -ne 0 || "$(jq -r '.status // "invalid"' "$query_file" 2>/dev/null)" != "fresh" ]]; then
  echo "DEPENDENCY_GRAPH=fail"
  echo "canonical graph is not fresh"
  cat "$query_file"
  exit 1
fi

jq -r '.facts[] | select(.kind == "dependency" and .inferred == false) | [(.dependency_detail.direction // ""), (.dependency_detail.kind // ""), (.payload.from_selector // .from), (.payload.to_selector // .to // "")] | @tsv' "$query_file" | sed '/^[[:space:]]*$/d' | sort -u >"$all_edges"
jq -r '.nodes[] | select(.layer == "source" and .payload.manifest_present == true) | .path' "$query_file" | sort -u >"$manifest_files"

collect_changed() {
  {
    git -C "$ROOT_DIR" diff --name-only --diff-filter=ACMRT HEAD --
    git -C "$ROOT_DIR" ls-files --others --exclude-standard
  } | sed '/^$/d'
}

if [[ ${#INPUT_PATHS[@]} -gt 0 ]]; then
  printf '%s\n' "${INPUT_PATHS[@]}" | sort -u >"$selected_file"
elif [[ "$CHANGED" -eq 1 ]]; then
  collect_changed | sort -u >"$selected_file"
fi

if [[ -s "$selected_file" ]]; then
  awk -F '\t' 'NR == FNR { selected[$0] = 1; next } selected[$3]' "$selected_file" "$all_edges" >"$edges_file"
  awk 'NR == FNR { selected[$0] = 1; next } selected[$0]' "$selected_file" "$manifest_files" >"$manifest_files.selected"
  mv "$manifest_files.selected" "$manifest_files"
else
  cp "$all_edges" "$edges_file"
fi

if [[ "$PRINT_EDGES" -eq 1 ]]; then
  cat "$edges_file"
fi
if [[ -n "$GRAPH_TSV_OUTPUT" ]]; then
  mkdir -p "$(dirname "$GRAPH_TSV_OUTPUT")"
  {
    printf 'direction\tkind\tsource\ttarget\n'
    cat "$edges_file"
  } >"$GRAPH_TSV_OUTPUT"
  echo "DEPENDENCY_GRAPH_TSV=$GRAPH_TSV_OUTPUT"
fi

focus_paths() {
  if [[ ${#FOCUS_PATHS[@]} -gt 0 ]]; then printf '%s\n' "${FOCUS_PATHS[@]}"; fi
  if [[ "$FOCUS_CHANGED" -eq 1 ]]; then collect_changed; fi
}

emit_related() {
  local focus="$1"
  echo "DEPENDENCY_RELATED_SURFACE=$focus"
  awk -F '\t' -v file="$focus" '
    $3 == file { printf "DEPENDENCY_RELATED_EDGE role=declared_%s kind=%s source=%s target=%s\n", $1, $2, $3, $4; found = 1 }
    $4 == file { printf "DEPENDENCY_RELATED_EDGE role=incoming_%s kind=%s source=%s target=%s\n", $1, $2, $3, $4; found = 1 }
    END { if (!found) printf "DEPENDENCY_RELATED_EDGE role=none path=%s\n", file }
  ' "$all_edges"
}

if [[ "$LIST_RELATED" -eq 1 ]]; then
  related_count=0
  while IFS= read -r focus; do
    [[ -n "$focus" ]] || continue
    emit_related "${focus#./}"
    related_count=$((related_count + 1))
  done < <(focus_paths | sort -u)
  echo "DEPENDENCY_RELATED_SURFACES=$related_count"
fi

scope_paths() {
  if [[ ${#EDIT_SCOPE_PATHS[@]} -gt 0 ]]; then printf '%s\n' "${EDIT_SCOPE_PATHS[@]}"; fi
  if [[ "$EDIT_SCOPE_CHANGED" -eq 1 ]]; then collect_changed; fi
  if [[ -n "$EDIT_SCOPE_HITS_FILE" ]]; then
    awk -F ':' 'NF { print $1 }' "$EDIT_SCOPE_HITS_FILE"
  fi
}

if [[ "$EDIT_SCOPE" -eq 1 ]]; then
  while IFS= read -r raw_focus; do
    [[ -n "$raw_focus" ]] || continue
    focus="${raw_focus#./}"
    printf 'DEPENDENCY_EDIT_SCOPE_PATH role=search_hit path=%s\n' "$focus"
    awk -F '\t' -v file="$focus" '
      $3 == file { printf "DEPENDENCY_EDIT_SCOPE_PATH role=declared_%s kind=%s path=%s source=%s target=%s\n", $1, $2, $4, $3, $4 }
      $4 == file { printf "DEPENDENCY_EDIT_SCOPE_PATH role=incoming_%s kind=%s path=%s source=%s target=%s\n", $1, $2, $3, $3, $4 }
    ' "$all_edges"
  done < <(scope_paths | sort -u) | sort -u >"$scope_file"
  cat "$scope_file"
  echo "DEPENDENCY_EDIT_SCOPE_PATHS=$(wc -l <"$scope_file" | tr -d ' ')"
fi

failures=0
while IFS= read -r manifest_file; do
  [[ -n "$manifest_file" ]] || continue
  if ! awk -F '\t' -v file="$manifest_file" '$3 == file || $4 == file { found = 1 } END { exit(found ? 0 : 1) }' "$edges_file"; then
    echo "$manifest_file: isolated dependency manifest has no graph edges"
    failures=$((failures + 1))
  fi
done <"$manifest_files"

while IFS=$'\t' read -r direction kind source target; do
  [[ -n "${direction:-}" ]] || continue
  if [[ "$source" == "$target" ]]; then
    echo "$source: self reference in $direction $kind edge"
    failures=$((failures + 1))
  fi
  if [[ "$CHECK_BIDIRECTIONAL" -eq 1 ]]; then
    if [[ "$direction" == "upstream" ]]; then reverse="downstream"; else reverse="upstream"; fi
    if ! awk -F '\t' -v d="$reverse" -v k="$kind" -v s="$target" -v t="$source" '$1 == d && $2 == k && $3 == s && $4 == t { found = 1 } END { exit(found ? 0 : 1) }' "$all_edges"; then
      echo "$source: missing reverse $reverse $kind edge from $target"
      failures=$((failures + 1))
    fi
  fi
done <"$edges_file"

check_cycles() {
  local direction="$1"
  awk -F '\t' -v wanted="$direction" '
    $1 == wanted { adj[$3] = adj[$3] SUBSEP $4; nodes[$3] = 1; nodes[$4] = 1 }
    function dfs(node, raw, parts, count, i, next_node) {
      state[node] = 1; raw = adj[node]; count = split(raw, parts, SUBSEP)
      for (i = 1; i <= count; i++) { next_node = parts[i]; if (next_node == "") continue; if (state[next_node] == 1) { print wanted " cycle includes " node " -> " next_node; found = 1; return } if (state[next_node] == 0) { dfs(next_node); if (found) return } }
      state[node] = 2
    }
    END { for (node in nodes) if (state[node] == 0) { dfs(node); if (found) exit 1 } }
  ' "$edges_file"
}

for direction in upstream downstream; do
  if ! check_cycles "$direction"; then
    if [[ "$CYCLE_REPORT_ONLY" -eq 1 ]]; then
      echo "DEPENDENCY_GRAPH_${direction^^}_CYCLES=report_only"
    else
      failures=$((failures + 1))
    fi
  fi
done

if [[ "$failures" -gt 0 ]]; then
  echo "DEPENDENCY_GRAPH=fail"
  exit 1
fi
echo "DEPENDENCY_GRAPH=pass authority=canonical-graph"
