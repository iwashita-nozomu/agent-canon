#!/usr/bin/env bash
# @dependency-start
# contract tool
# responsibility Projects and validates dependency relations captured by the canonical graph.
# upstream design ../../documents/design/dependency-manifest-design.md dependency graph semantics
# upstream implementation ../../rust/agent-canon/src/graph.rs owns dependency parsing, binding, and storage
# upstream implementation ./parent_root_side_effects.py owns graph scratch and TSV publication
# upstream implementation ../lib/repo_paths.sh resolves the physical analyzer tool root
# downstream implementation ./render_dependency_manifest_graph.py renders exported dependency TSV
# @dependency-end
set -euo pipefail

INVOCATION_SCRIPT="$(realpath -e "${BASH_SOURCE[0]}" 2>/dev/null || true)"
BOUNDARY_SCRIPT="$(dirname "$INVOCATION_SCRIPT")/parent_root_side_effects.py"
if [[ -z "${AGENT_CANON_SIDE_EFFECT_HANDOFF:-}" ]]; then
  if [[ -z "$INVOCATION_SCRIPT" || ! -f "$INVOCATION_SCRIPT" ]]; then
    echo "DEPENDENCY_GRAPH=fail reason=invocation_script_missing" >&2
    exit 2
  fi
  exec python3 "$BOUNDARY_SCRIPT" public-exec \
    --invocation-script "$INVOCATION_SCRIPT" \
    --purpose dependency-graph \
    -- bash "$INVOCATION_SCRIPT" "$@"
fi

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
ENSURE_GRAPH=0
ANALYZER_TOOLS_ROOT_OVERRIDE=""
declare -a INPUT_PATHS=()
declare -a FOCUS_PATHS=()
declare -a EDIT_SCOPE_PATHS=()

usage() {
  cat <<'EOF'
Usage:
  check_dependency_graph.sh [--root DIR] [--analyzer-tools-root DIR] [--ensure-graph] [--changed] [--print-edges] [--graph-tsv PATH] [--list-related] [--focus PATH] [--focus-changed] [--edit-scope PATH] [--edit-scope-changed] [--search-hits-file PATH] [--check-bidirectional] [--cycle-report-only] [paths...]

  Consumes one canonical graph query; it does not parse source manifests.
  --ensure-graph owns the explicit status/build/status readiness route and
  exits before querying or projecting dependency relations.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --root) ROOT_DIR="$2"; shift 2 ;;
    --analyzer-tools-root) ANALYZER_TOOLS_ROOT_OVERRIDE="$2"; shift 2 ;;
    --ensure-graph) ENSURE_GRAPH=1; shift ;;
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

ROOT_DIR="$(realpath -e "$ROOT_DIR")" || {
  echo "DEPENDENCY_GRAPH=fail reason=target_root_missing" >&2
  exit 2
}
PARENT_ROOT="${AGENT_CANON_SIDE_EFFECT_PARENT_ROOT:-$(git -C "$PWD" rev-parse --show-toplevel 2>/dev/null || true)}"
if [[ -z "$PARENT_ROOT" ]]; then
  echo "DEPENDENCY_GRAPH=fail reason=missing-parent-root" >&2
  exit 1
fi
if [[ -n "${AGENT_CANON_SIDE_EFFECT_PARENT_ROOT:-}" && -z "${AGENT_CANON_SIDE_EFFECT_HANDOFF:-}" ]]; then
  echo "DEPENDENCY_GRAPH=fail reason=side_effect_session_missing" >&2
  exit 2
fi
PARENT_ROOT="$(realpath -e "$PARENT_ROOT")" || {
  echo "DEPENDENCY_GRAPH=fail reason=parent_root_missing" >&2
  exit 2
}
CANON_SCRIPT_PATH="$INVOCATION_SCRIPT"
if [[ -z "$CANON_SCRIPT_PATH" || ! -f "$CANON_SCRIPT_PATH" ]]; then
  echo "DEPENDENCY_GRAPH=fail reason=invocation_script_missing" >&2
  exit 2
fi
source "$(dirname "$CANON_SCRIPT_PATH")/../lib/repo_paths.sh"
ANALYZER_TOOLS_ROOT="$(agent_canon_analyzer_tools_root \
  "$CANON_SCRIPT_PATH" "$ANALYZER_TOOLS_ROOT_OVERRIDE" "$PARENT_ROOT" \
  "${AGENT_CANON_ANALYZER_TOOLS_ROOT_PHYSICAL_DEFAULT:-0}" \
  bin/agent-canon)" || {
  echo "DEPENDENCY_GRAPH=fail reason=analyzer_tools_root_invalid" >&2
  exit 2
}
GRAPH_CLI="$ANALYZER_TOOLS_ROOT/bin/agent-canon"
export PYTHONDONTWRITEBYTECODE=1
echo "DEPENDENCY_GRAPH_ANALYZER_TOOLS_ROOT=$ANALYZER_TOOLS_ROOT"
TEMP_ROOT="$(
  python3 "$BOUNDARY_SCRIPT" temp-dir \
    --root "$PARENT_ROOT" \
    --candidate "${AGENT_CANON_PARENT_TMPDIR:-$PARENT_ROOT/.agent-canon/tmp}" \
    --prefix dependency-graph. \
    --purpose dependency-graph
)"

status_file="$TEMP_ROOT/status.json"
query_file="$TEMP_ROOT/query.json"
all_edges="$TEMP_ROOT/all-edges.tsv"
edges_file="$TEMP_ROOT/edges.tsv"
manifest_files="$TEMP_ROOT/manifest.txt"
selected_file="$TEMP_ROOT/selected.txt"
scope_file="$TEMP_ROOT/scope.txt"

cleanup_dependency_graph_temp() {
  local status=$?
  local cleanup_status=0
  trap - EXIT
  python3 "$BOUNDARY_SCRIPT" remove-tree \
    --root "$PARENT_ROOT" \
    --candidate "$TEMP_ROOT" \
    --purpose dependency-graph-cleanup >/dev/null || cleanup_status=$?
  if [[ "$status" -eq 0 && "$cleanup_status" -ne 0 ]]; then
    status=$cleanup_status
  fi
  exit "$status"
}
trap cleanup_dependency_graph_temp EXIT

run_graph_status() {
  local status_rc=0
  if "$GRAPH_CLI" graph status --root "$ROOT_DIR" --profile default --format json >"$status_file"; then
    status_rc=0
  else
    status_rc=$?
  fi
  status_schema="$(jq -r 'if (.schema | type) == "string" then .schema else "invalid" end' "$status_file" 2>/dev/null || true)"
  status_command="$(jq -r 'if (.command | type) == "string" then .command else "invalid" end' "$status_file" 2>/dev/null || true)"
  status_name="$(jq -r 'if (.status | type) == "string" then .status else "invalid" end' "$status_file" 2>/dev/null || true)"
  status_record_exit="$(jq -r 'if ((.exit_code | type) == "number" and .exit_code == (.exit_code | floor)) then (.exit_code | tostring) else "invalid" end' "$status_file" 2>/dev/null || true)"
  status_reason="$(jq -r 'if .reason == null then "null" elif (.reason | type) == "string" then .reason else "invalid" end' "$status_file" 2>/dev/null || true)"
  status_probe_reason="$(jq -r 'if .probe_reason == null then "null" elif (.probe_reason | type) == "string" then .probe_reason else "invalid" end' "$status_file" 2>/dev/null || true)"
  status_schema="${status_schema:-invalid}"
  status_command="${status_command:-invalid}"
  status_name="${status_name:-invalid}"
  status_record_exit="${status_record_exit:-invalid}"
  status_reason="${status_reason:-invalid}"
  status_probe_reason="${status_probe_reason:-invalid}"
  printf '%s\n' "GRAPH_STATUS_RC=${status_rc}"
  cat "$status_file"
  return "$status_rc"
}

if run_graph_status; then
  status_exit=0
else
  status_exit=$?
fi
status_binding="${status_exit}:${status_schema}:${status_command}:${status_name}:${status_record_exit}:${status_reason}:${status_probe_reason}"
fresh_binding="0:agent-canon.graph.status.v1:status:fresh:0:null:null"
source_changed_binding="2:agent-canon.graph.status.v1:status:stale:2:source_changed:source_changed"
if [[ "$status_binding" == "$fresh_binding" ]]; then
  echo "GRAPH_REBUILD=not_needed"
elif [[ "$ENSURE_GRAPH" -eq 1 && "$status_binding" == "$source_changed_binding" ]]; then
  echo "GRAPH_REBUILD=required status=stale reason=source_changed probe_reason=source_changed"
  set +e
  "$GRAPH_CLI" graph build --root "$ROOT_DIR" --profile default --format json
  build_exit=$?
  set -e
  if [[ "$build_exit" -ne 0 && "$build_exit" -ne 1 ]]; then
    echo "DEPENDENCY_GRAPH=fail"
    echo "REPO_DEPENDENCY_REVIEW=fail"
    echo "GRAPH_REBUILD=failed rc=${build_exit}"
    exit "$build_exit"
  fi
  echo "GRAPH_REBUILD=performed"
  if run_graph_status; then
    status_exit=0
  else
    status_exit=$?
  fi
  status_binding="${status_exit}:${status_schema}:${status_command}:${status_name}:${status_record_exit}:${status_reason}:${status_probe_reason}"
else
  echo "GRAPH_REBUILD=not_admitted status=${status_name} reason=${status_reason} probe_reason=${status_probe_reason}"
fi
if [[ "$status_binding" != "$fresh_binding" ]]; then
  echo "DEPENDENCY_GRAPH=fail"
  echo "REPO_DEPENDENCY_REVIEW=fail"
  echo "canonical graph is not fresh"
  cat "$status_file"
  exit 1
fi
if [[ "$ENSURE_GRAPH" -eq 1 ]]; then
  echo "GRAPH_ENSURE=pass status=fresh"
  exit 0
fi

set +e
"$GRAPH_CLI" graph query --root "$ROOT_DIR" --profile default --format json --all --relation all --direction both --depth 0 >"$query_file"
query_exit=$?
set -e
if [[ "$query_exit" -ne 0 || "$(jq -r '.status // "invalid"' "$query_file" 2>/dev/null)" != "fresh" ]]; then
  echo "DEPENDENCY_GRAPH=fail"
  echo "REPO_DEPENDENCY_REVIEW=fail"
  echo "canonical graph is not fresh"
  cat "$query_file"
  exit 1
fi

jq -r '
  (.nodes | map({key: .id, value: .path}) | from_entries) as $node_paths
  | .facts[]
  | select(.kind == "dependency" and .inferred == false)
  | [
      (.dependency_detail.direction // ""),
      (.dependency_detail.kind // ""),
      ($node_paths[.from] // ""),
      ($node_paths[.to] // "")
    ]
  | @tsv
' "$query_file" | sort -u >"$all_edges"
jq -r '.nodes[] | select(.layer == "source" and .payload.manifest_present == true) | .path' "$query_file" | sort -u >"$manifest_files"

failures=0
while IFS= read -r projection_error; do
  [[ -n "$projection_error" ]] || continue
  echo "$projection_error"
  failures=$((failures + 1))
done < <(
  awk -F '\t' '
    function display(value) { return value == "" ? "<empty>" : value }
    $3 == "" || $4 == "" {
      printf "dependency graph projection has unresolved endpoint: source=%s target=%s\n", display($3), display($4)
      next
    }
    $1 == "" || $2 == "" {
      printf "dependency graph projection has incomplete relation: direction=%s kind=%s source=%s target=%s\n", display($1), display($2), $3, $4
    }
  ' "$all_edges"
)

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
  graph_output_staging="$TEMP_ROOT/graph-output.tsv"
  {
    printf 'direction\tkind\tsource\ttarget\n'
    cat "$edges_file"
  } >"$graph_output_staging"
  python3 "$BOUNDARY_SCRIPT" write \
    --root "$PARENT_ROOT" \
    --candidate "$GRAPH_TSV_OUTPUT" \
    --purpose dependency-graph-output <"$graph_output_staging" >/dev/null
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

while IFS= read -r manifest_file; do
  [[ -n "$manifest_file" ]] || continue
  if ! awk -F '\t' -v file="$manifest_file" '$3 == file || $4 == file { found = 1 } END { exit(found ? 0 : 1) }' "$edges_file"; then
    echo "$manifest_file: isolated dependency manifest has no graph edges"
    failures=$((failures + 1))
  fi
done <"$manifest_files"

while IFS=$'\t' read -r direction kind source target; do
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
done < <(awk -F '\t' '$1 != "" && $2 != "" && $3 != "" && $4 != ""' "$edges_file")

check_cycles() {
  local direction="$1"
  awk -F '\t' -v wanted="$direction" '
    $1 == wanted && $2 != "" && $3 != "" && $4 != "" { adj[$3] = adj[$3] SUBSEP $4; nodes[$3] = 1; nodes[$4] = 1 }
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
