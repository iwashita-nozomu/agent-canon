#!/usr/bin/env bash
# @dependency-start
# contract tool
# responsibility Projects and validates dependency relations directly from tracked source manifests.
# upstream design ../../documents/design/source-owned-dependency-validation.md source-derived graph projection authority
# upstream design ../../documents/design/dependency-manifest-design.md dependency graph semantics
# upstream design ../../documents/design/source-owned-dependency-validation.md tracked source authority boundary
# upstream implementation ./source_dependency_graph.py owns source parsing, canonical binding, and review export
# upstream implementation ./runtime_artifacts.py owns external graph scratch and TSV publication
# downstream implementation ./render_dependency_manifest_graph.py renders exported dependency TSV
# downstream implementation ../../tests/agent_tools/test_dependency_manifest_tools.py verifies source-derived graph review
# @dependency-end
set -euo pipefail

ROOT_DIR="$(git -C "$PWD" rev-parse --show-toplevel 2>/dev/null || pwd)"
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
RUNTIME_ROOT="${AGENT_CANON_RUNTIME_ROOT:-}"
CONTROL_ROOT="${AGENT_CANON_CONTROL_PARENT_ROOT:-}"
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

fail_runtime_boundary() {
  echo "DEPENDENCY_GRAPH=fail reason=$1" >&2
  return 2
}

runtime_path() {
  local candidate="$1"
  python3 - "$script_dir" "$ROOT_DIR" "$CONTROL_ROOT" "$RUNTIME_ROOT" "$candidate" <<'PY'
from pathlib import Path
import sys

source, root, control, runtime, candidate = map(Path, sys.argv[1:])
sys.path.insert(0, str(source.parents[2].resolve(strict=True)))
from tools.runtime.artifacts.runtime_artifacts import RuntimeArtifactBoundary, RuntimeArtifactError

try:
    source_root = source.parents[2].resolve(strict=True)
    target_root = root.resolve(strict=True)
    control_root = control.resolve(strict=True)
    boundary = RuntimeArtifactBoundary.for_source(source_root, runtime, create=True)
    if boundary.root == target_root or boundary.root in target_root.parents:
        raise RuntimeArtifactError("runtime root must be outside target repository")
    try:
        target_root.relative_to(control_root)
    except ValueError as exc:
        raise RuntimeArtifactError("target repository is outside control root") from exc
    print(boundary.resolve(candidate))
except (OSError, RuntimeArtifactError, ValueError) as exc:
    print(f"runtime boundary invalid: {exc}", file=sys.stderr)
    raise SystemExit(2)
PY
}

write_runtime_file() {
  local candidate="$1"
  local source_file="$2"
  python3 - "$script_dir" "$RUNTIME_ROOT" "$candidate" "$source_file" <<'PY'
from pathlib import Path
import sys

source, runtime, candidate, source_file = map(Path, sys.argv[1:])
sys.path.insert(0, str(source.parents[2].resolve(strict=True)))
from tools.runtime.artifacts.runtime_artifacts import RuntimeArtifactBoundary, RuntimeArtifactError

try:
    boundary = RuntimeArtifactBoundary.for_source(
        source.parents[2].resolve(strict=True), runtime, create=True
    )
    boundary.atomic_write_bytes(boundary.resolve(candidate), source_file.read_bytes())
except (OSError, RuntimeArtifactError, ValueError) as exc:
    print(f"runtime boundary invalid: {exc}", file=sys.stderr)
    raise SystemExit(2)
PY
}

require_runtime_boundary() {
  [[ -n "$RUNTIME_ROOT" ]] || { fail_runtime_boundary "runtime_root_required"; return 2; }
  [[ -n "$CONTROL_ROOT" ]] || { fail_runtime_boundary "control_root_required"; return 2; }
  [[ -d "$CONTROL_ROOT" ]] || { fail_runtime_boundary "control_root_missing"; return 2; }
  runtime_path .runtime-boundary-probe >/dev/null || return 2
}

usage() {
  cat <<'EOF'
Usage:
  check_dependency_graph.sh [--root DIR] [--changed] [--print-edges] [--graph-tsv PATH] [--list-related] [--focus PATH] [--focus-changed] [--edit-scope PATH] [--edit-scope-changed] [--search-hits-file PATH] [--check-bidirectional] [--cycle-report-only] [paths...]

Consumes deterministic dependency facts derived from tracked source manifests.
It does not build, query, or read persisted graph runtime state.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --root) ROOT_DIR="$2"; shift 2 ;;
    --changed) CHANGED=1; shift ;;
    --print-edges) PRINT_EDGES=1; shift ;;
    --graph-tsv) GRAPH_TSV_OUTPUT="$2"; shift 2 ;;
    --list-related) LIST_RELATED=1; shift ;;
    --focus) FOCUS_PATHS+=("$2"); shift 2 ;;
    --focus-changed) FOCUS_CHANGED=1; shift ;;
    --edit-scope) EDIT_SCOPE=1; EDIT_SCOPE_PATHS+=("$2"); shift 2 ;;
    --edit-scope-changed) EDIT_SCOPE=1; EDIT_SCOPE_CHANGED=1; shift ;;
    --search-hits-file) EDIT_SCOPE=1; EDIT_SCOPE_HITS_FILE="$2"; shift 2 ;;
    --check-bidirectional) CHECK_BIDIRECTIONAL=1; shift ;;
    --cycle-report-only) CYCLE_REPORT_ONLY=1; shift ;;
    --allow-frontmatter) shift ;;
    -h|--help) usage; exit 0 ;;
    *) INPUT_PATHS+=("$1"); shift ;;
  esac
done

ROOT_DIR="$(realpath -e "$ROOT_DIR")" || {
  echo "DEPENDENCY_GRAPH=fail reason=root-missing" >&2
  exit 1
}
require_runtime_boundary || exit $?
export AGENT_CANON_RUNTIME_ROOT="$RUNTIME_ROOT"
export AGENT_CANON_CONTROL_PARENT_ROOT="$CONTROL_ROOT"

normalize_repo_path() {
  local raw="$1"
  local absolute=""
  # Selector identities are lexical repository paths. Canonical source parsing
  # owns symlink binding and physical dependency-target containment.
  if [[ "$raw" = /* ]]; then
    absolute="$(realpath -m --no-symlinks "$raw")"
  else
    absolute="$(realpath -m --no-symlinks "$ROOT_DIR/${raw#./}")"
  fi
  case "$absolute" in
    "$ROOT_DIR") printf '.\n' ;;
    "$ROOT_DIR"/*) printf '%s\n' "${absolute#"$ROOT_DIR"/}" ;;
    *)
      echo "DEPENDENCY_GRAPH=fail reason=path-outside-root path=$raw" >&2
      return 1
      ;;
  esac
}

normalize_path_array() {
  local array_name="$1"
  local -n values="$array_name"
  local -a normalized=()
  local value=""
  for value in "${values[@]}"; do
    normalized+=("$(normalize_repo_path "$value")")
  done
  values=("${normalized[@]}")
}

normalize_path_array INPUT_PATHS
normalize_path_array FOCUS_PATHS
normalize_path_array EDIT_SCOPE_PATHS

CANON_SCRIPT_PATH="$(realpath -m "${BASH_SOURCE[0]}")"
TOOL_DIR="$(dirname "$CANON_SCRIPT_PATH")"
SOURCE_GRAPH_TOOL="${TOOL_DIR}/source_dependency_graph.py"
TEMP_BASE="$(runtime_path tmp/dependency-graph)" || exit $?
mkdir -p "$TEMP_BASE"
TEMP_ROOT="$(mktemp -d "$TEMP_BASE/run.XXXXXX")"

all_edges="$TEMP_ROOT/all-edges.tsv"
edges_file="$TEMP_ROOT/edges.tsv"
manifest_files="$TEMP_ROOT/manifest.txt"
selected_file="$TEMP_ROOT/selected.txt"
scope_file="$TEMP_ROOT/scope.txt"

cleanup_dependency_graph_temp() {
  local status=$?
  local cleanup_status=0
  trap - EXIT
  if [[ -d "$TEMP_ROOT" ]]; then
    rm -rf -- "$TEMP_ROOT" || cleanup_status=$?
  fi
  if [[ "$status" -eq 0 && "$cleanup_status" -ne 0 ]]; then
    status=$cleanup_status
  fi
  exit "$status"
}
trap cleanup_dependency_graph_temp EXIT

if ! python3 "$SOURCE_GRAPH_TOOL" \
  --root "$ROOT_DIR" \
  --edges-out "$all_edges" \
  --manifests-out "$manifest_files"; then
  echo "DEPENDENCY_GRAPH=fail"
  exit 1
fi

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
  write_runtime_file "$GRAPH_TSV_OUTPUT" "$graph_output_staging"
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
    emit_related "$(normalize_repo_path "$focus")"
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
    focus="$(normalize_repo_path "$raw_focus")"
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
echo "DEPENDENCY_GRAPH=pass authority=tracked-source"
