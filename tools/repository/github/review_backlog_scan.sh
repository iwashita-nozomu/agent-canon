#!/usr/bin/env bash
# @dependency-start
# contract tool
# responsibility Runs integrated backlog-review scans across root and AgentCanon scopes.
# upstream implementation ./file_surface_inventory.py writes inventory reports
# upstream implementation ./run_repo_dependency_review.sh validates dependency manifests
# upstream implementation ./scan_code_dependencies.sh extracts code dependency edges
# upstream implementation ../oop/python/readability.py writes Python OOP readability reports
# upstream implementation ../oop/cpp/readability.py writes C++ OOP readability reports
# downstream design ../../tools/README.md documents the review backlog scan entrypoint
# @dependency-end
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENT_CANON_SOURCE_ROOT="$(realpath -m "$SCRIPT_DIR/../..")"
ROOT_DIR="$(git -C "$PWD" rev-parse --show-toplevel 2>/dev/null || pwd)"
REPORT_DIR=""
RUNTIME_ROOT="${AGENT_CANON_RUNTIME_ROOT:-}"
CONTROL_ROOT="${AGENT_CANON_CONTROL_PARENT_ROOT:-}"
SCOPE_MODE="root-only"
FAIL_ON_FINDINGS=0
SEMANTIC_QUERY_FILE=""
SEMANTIC_TOP_K=20
SEMANTIC_MIN_SCORE=0.90
SEMANTIC_LLM_PROVIDER="${AGENT_CANON_SEMANTIC_INDEX_LLM_PROVIDER:-}"
SEMANTIC_LLM_MODEL="${AGENT_CANON_SEMANTIC_INDEX_LLM_MODEL:-}"
SEMANTIC_LLM_URL="${AGENT_CANON_SEMANTIC_INDEX_EMBEDDING_URL:-}"
SEMANTIC_LLM_DIM="${AGENT_CANON_SEMANTIC_INDEX_LLM_DIM:-0}"
SEMANTIC_LLM_BATCH="${AGENT_CANON_SEMANTIC_INDEX_LLM_BATCH:-16}"
declare -a REQUESTED_CHECKS=()

fail_runtime_boundary() {
  echo "REVIEW_BACKLOG_SCAN=fail reason=$1" >&2
  exit 2
}

require_runtime_boundary() {
  [[ -n "$RUNTIME_ROOT" ]] || fail_runtime_boundary "runtime_root_required"
  [[ -n "$CONTROL_ROOT" ]] || fail_runtime_boundary "control_root_required"
  [[ -d "$CONTROL_ROOT" ]] || fail_runtime_boundary "control_root_missing"
  python3 - "$AGENT_CANON_SOURCE_ROOT" "$ROOT_DIR" "$CONTROL_ROOT" "$RUNTIME_ROOT" <<'PY'
from pathlib import Path
import sys

source, root, control, runtime = map(Path, sys.argv[1:])
sys.path.insert(0, str(source / "tools" / "agent_tools"))
from runtime_artifacts import (
    RuntimeArtifactBoundary,
    RuntimeArtifactError,
)

try:
    source = source.resolve(strict=True)
    root = root.resolve(strict=True)
    control = control.resolve(strict=True)
    # This is a preflight only.  Do not create the runtime root until every
    # caller-controlled output override has been validated below.
    boundary = RuntimeArtifactBoundary.for_source(source, runtime, create=False)
    runtime_resolved = boundary.root
    if runtime_resolved == root or root in runtime_resolved.parents:
        raise RuntimeArtifactError("runtime root must be outside target repository")
    try:
        root.relative_to(control)
    except ValueError as exc:
        raise RuntimeArtifactError("target repository is outside control root") from exc
except (OSError, RuntimeArtifactError, ValueError) as exc:
    print(f"runtime boundary invalid: {exc}", file=sys.stderr)
    raise SystemExit(2)
print(runtime_resolved)
PY
}

runtime_path() {
  local candidate="$1"
  python3 - "$AGENT_CANON_SOURCE_ROOT" "$ROOT_DIR" "$RUNTIME_ROOT" "$candidate" <<'PY'
from pathlib import Path
import sys

source, root, runtime, candidate = map(Path, sys.argv[1:])
sys.path.insert(0, str(source / "tools" / "agent_tools"))
from runtime_artifacts import RuntimeArtifactBoundary, RuntimeArtifactError

try:
    # Path validation must be side-effect free.  In particular, an invalid
    # report/target/CLI override must not create the runtime root first.
    boundary = RuntimeArtifactBoundary.for_source(source, runtime, create=False)
    resolved_root = root.resolve(strict=True)
    target = boundary.resolve(candidate)
    if target == resolved_root or resolved_root in target.parents:
        raise RuntimeArtifactError("runtime artifact must not be inside target repository")
except (OSError, RuntimeArtifactError, ValueError) as exc:
    print(f"runtime path invalid: {exc}", file=sys.stderr)
    raise SystemExit(2)
print(target)
PY
}

materialize_runtime_boundary() {
  python3 - "$AGENT_CANON_SOURCE_ROOT" "$RUNTIME_ROOT" <<'PY'
from pathlib import Path
import sys

source, runtime = map(Path, sys.argv[1:])
sys.path.insert(0, str(source / "tools" / "agent_tools"))
from runtime_artifacts import RuntimeArtifactBoundary

RuntimeArtifactBoundary.for_source(source, runtime, create=True)
PY
}

usage() {
  cat <<'EOF'
Usage:
  review_backlog_scan.sh [--root DIR] [--report-dir DIR]
                         [--root-only]
                         [--semantic-query-file FILE]
                         [--semantic-top-k N] [--semantic-min-score SCORE]
                         [--semantic-llm-provider NAME --semantic-llm-model NAME]
                         [--semantic-embedding-url URL]
                         [--check NAME ...] [--fail-on-findings]

Runs integrated review scans and writes JSON/Markdown/log artifacts under REPORT_DIR.
The selected checkout is the only scan scope. Default checks are all checks.

Checks:
  inventory, stale, code-dependencies, dependency-review, oop,
  static-any, hardcoded-numbers, log-helper, convention, semantic-index
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --root)
      ROOT_DIR="$2"
      shift 2
      ;;
    --report-dir)
      REPORT_DIR="$2"
      shift 2
      ;;
    --root-only)
      SCOPE_MODE="root-only"
      shift
      ;;
    --check)
      REQUESTED_CHECKS+=("$2")
      shift 2
      ;;
    --semantic-query-file)
      SEMANTIC_QUERY_FILE="$2"
      shift 2
      ;;
    --semantic-top-k)
      SEMANTIC_TOP_K="$2"
      shift 2
      ;;
    --semantic-min-score)
      SEMANTIC_MIN_SCORE="$2"
      shift 2
      ;;
    --semantic-llm-provider)
      SEMANTIC_LLM_PROVIDER="$2"
      shift 2
      ;;
    --semantic-llm-model)
      SEMANTIC_LLM_MODEL="$2"
      shift 2
      ;;
    --semantic-embedding-url)
      SEMANTIC_LLM_URL="$2"
      shift 2
      ;;
    --semantic-llm-dim)
      SEMANTIC_LLM_DIM="$2"
      shift 2
      ;;
    --semantic-embedding-batch)
      SEMANTIC_LLM_BATCH="$2"
      shift 2
      ;;
    --fail-on-findings)
      FAIL_ON_FINDINGS=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

ROOT_DIR="$(realpath -e "$ROOT_DIR")" || fail_runtime_boundary "target_root_missing"
CONTROL_ROOT="$(realpath -e "$CONTROL_ROOT")" || fail_runtime_boundary "control_root_missing"
RUNTIME_ROOT="$(require_runtime_boundary)" || exit $?
export AGENT_CANON_RUNTIME_ROOT="$RUNTIME_ROOT"
export AGENT_CANON_CONTROL_PARENT_ROOT="$CONTROL_ROOT"
if [[ -z "$REPORT_DIR" ]]; then
  REPORT_DIR="reports/review-backlog-scan"
fi
REPORT_DIR="$(runtime_path "$REPORT_DIR")"
if [[ -n "$SEMANTIC_QUERY_FILE" ]]; then
  SEMANTIC_QUERY_FILE="$(realpath -m "$SEMANTIC_QUERY_FILE")"
fi
TOOL_DIR="$AGENT_CANON_SOURCE_ROOT/tools/agent_tools"
REVIEW_SCAN_TARGET_DIR="${AGENT_CANON_REVIEW_SCAN_TARGET_DIR:-review-scan-target}"
REVIEW_SCAN_TARGET_DIR="$(runtime_path "$REVIEW_SCAN_TARGET_DIR")"
if [[ -n "${AGENT_CANON_CLI:-}" ]]; then
  AGENT_CANON_CLI="$(realpath -e "$AGENT_CANON_CLI")" || fail_runtime_boundary "agent_canon_cli_missing"
else
  AGENT_CANON_CLI="$(command -v agent-canon || true)"
fi
# All host-side Python checks are read-only with respect to the source tree.
# Their reports and caches are already redirected to the external runtime.
export PYTHONDONTWRITEBYTECODE=1
materialize_runtime_boundary
mkdir -p "$REPORT_DIR"
REVIEW_SCAN_TARGET_READY=0
REPORT="$REPORT_DIR/review_backlog_scan.md"
COMMAND_STATUS="$REPORT_DIR/review_backlog_scan_status.tsv"
NONZERO_COMMANDS=0

if [[ ${#REQUESTED_CHECKS[@]} -eq 0 ]]; then
  REQUESTED_CHECKS=(
    inventory
    stale
    code-dependencies
    dependency-review
    oop
    static-any
    hardcoded-numbers
    log-helper
    convention
    semantic-index
  )
fi

has_check() {
  local wanted="$1"
  local check
  for check in "${REQUESTED_CHECKS[@]}"; do
    [[ "$check" == "$wanted" ]] && return 0
  done
  return 1
}

scope_args() {
  printf '%s\n' "--root-only"
}

scope_roots() {
  printf 'root\t%s\n' "$ROOT_DIR"
}

record_command() {
  local name="$1"
  local outfile="$2"
  shift 2
  set +e
  "$@" >"$outfile" 2>&1
  local status=$?
  set -e
  printf '%s\t%s\t%s\n' "$name" "$status" "$outfile" >>"$COMMAND_STATUS"
  if [[ "$status" -ne 0 ]]; then
    NONZERO_COMMANDS=$((NONZERO_COMMANDS + 1))
  fi
}

ensure_review_scan_target() {
  if [[ "$REVIEW_SCAN_TARGET_READY" -eq 0 ]]; then
    mkdir -p "$REVIEW_SCAN_TARGET_DIR"
    REVIEW_SCAN_TARGET_READY=1
  fi
}

run_agent_canon() {
  ensure_review_scan_target
  if [[ -z "$AGENT_CANON_CLI" || ! -x "$AGENT_CANON_CLI" ]]; then
    echo "REVIEW_BACKLOG_SCAN=fail reason=runtime_cli_missing path=$AGENT_CANON_CLI" >&2
    return 127
  fi
  AGENT_CANON_RUNTIME_ROOT="$RUNTIME_ROOT" \
    AGENT_CANON_CONTROL_PARENT_ROOT="$CONTROL_ROOT" \
    CARGO_TARGET_DIR="$REVIEW_SCAN_TARGET_DIR" \
    "$AGENT_CANON_CLI" "$@"
}

run_inventory() {
  local scope_flag
  scope_flag="$(scope_args)"
  record_command \
    "inventory" \
    "$REPORT_DIR/file_surface_inventory.log" \
    python3 "$TOOL_DIR/file_surface_inventory.py" \
      --root "$ROOT_DIR" \
      "$scope_flag" \
      --json-out "$REPORT_DIR/file_surface_inventory.json" \
      --markdown-out "$REPORT_DIR/file_surface_inventory.md"
}

run_stale_search() {
  local output="$REPORT_DIR/stale_wording_search.txt"
  if command -v rg >/dev/null 2>&1; then
    set +e
    rg --no-messages --glob '!.git/**' --glob '!reports/**' --glob '!vendor/**/.git/**' \
      -n "subtree|snapshot copy|TODO|FIXME|old format|legacy format" \
      "$ROOT_DIR" >"$output" 2>&1
    local status=$?
    set -e
    if [[ "$status" -eq 1 ]]; then
      status=0
      printf '%s\n' "STALE_WORDING_SEARCH=no-matches" >>"$output"
    elif [[ "$status" -eq 2 ]]; then
      status=0
      printf '%s\n' "STALE_WORDING_SEARCH=warning rg-status-2-treated-as-report" >>"$output"
    fi
    printf '%s\t%s\t%s\n' "stale" "$status" "$output" >>"$COMMAND_STATUS"
    if [[ "$status" -ne 0 ]]; then
      NONZERO_COMMANDS=$((NONZERO_COMMANDS + 1))
    fi
  else
    set +e
    grep -RInE --exclude-dir=.git --exclude-dir=reports --exclude-dir=vendor \
      "subtree|snapshot copy|TODO|FIXME|old format|legacy format" \
      "$ROOT_DIR" >"$output" 2>&1
    local status=$?
    set -e
    if [[ "$status" -eq 1 ]]; then
      status=0
      printf '%s\n' "STALE_WORDING_SEARCH=no-matches" >>"$output"
    fi
    printf '%s\t%s\t%s\n' "stale" "$status" "$output" >>"$COMMAND_STATUS"
    if [[ "$status" -ne 0 ]]; then
      NONZERO_COMMANDS=$((NONZERO_COMMANDS + 1))
    fi
  fi
}

run_scope_checks() {
  local scope_name scope_root paths excludes
  while IFS=$'\t' read -r scope_name scope_root; do
    [[ -n "$scope_name" && -n "$scope_root" ]] || continue
    paths=(python include src tools tests mcp)
    excludes=(--exclude reports --exclude legacy)
    if has_check code-dependencies; then
      record_command \
        "code-dependencies:${scope_name}" \
        "$REPORT_DIR/code_dependencies_${scope_name}.txt" \
        bash "$TOOL_DIR/scan_code_dependencies.sh" \
          --root "$scope_root" \
          --analysis-json "$REPORT_DIR/code_analysis_${scope_name}.json"
    fi
    if has_check dependency-review; then
      record_command \
        "dependency-review:${scope_name}" \
        "$REPORT_DIR/dependency_review_${scope_name}.txt" \
        bash "$TOOL_DIR/run_repo_dependency_review.sh" \
          --root "$scope_root" \
          --report-dir "$REPORT_DIR/dependency-review-${scope_name}" \
          --fail-missing
    fi
    if has_check oop; then
      record_command \
        "oop-python:${scope_name}" \
        "$REPORT_DIR/oop_python_readability_${scope_name}.md" \
        python3 "$AGENT_CANON_SOURCE_ROOT/tools/validation/code/oop/python/readability.py" \
          --root "$scope_root" \
          --format markdown \
          --include-snippets \
          --exclude .git \
          "${excludes[@]}" \
          "${paths[@]}"
      record_command \
        "oop-cpp:${scope_name}" \
        "$REPORT_DIR/oop_cpp_readability_${scope_name}.md" \
        python3 "$AGENT_CANON_SOURCE_ROOT/tools/validation/code/oop/cpp/readability.py" \
          --root "$scope_root" \
          --format markdown \
          --include-snippets \
          --exclude .git \
          "${excludes[@]}" \
          "${paths[@]}"
    fi
    if has_check static-any; then
      record_command \
        "static-any:${scope_name}" \
        "$REPORT_DIR/static_any_${scope_name}.txt" \
        python3 "$TOOL_DIR/check_static_any.py" \
          --root "$scope_root" \
          --exclude reports \
          "${paths[@]}"
    fi
    if has_check hardcoded-numbers; then
      record_command \
        "hardcoded-numbers:${scope_name}" \
        "$REPORT_DIR/hardcoded_numbers_${scope_name}.txt" \
        python3 "$TOOL_DIR/check_hardcoded_numbers.py" \
          --root "$scope_root" \
          --format text \
          --no-fail-on-findings \
          "${excludes[@]}" \
          "${paths[@]}"
    fi
    if has_check log-helper; then
      record_command \
        "log-helper:${scope_name}" \
        "$REPORT_DIR/log_helper_names_${scope_name}.txt" \
        python3 "$TOOL_DIR/check_log_helper_names.py" \
          --root "$scope_root" \
          "${excludes[@]}" \
          "${paths[@]}"
    fi
  done < <(scope_roots)
}

run_semantic_index() {
  local scope_name scope_root db eval_args compare_args embed_args
  while IFS=$'\t' read -r scope_name scope_root; do
    [[ -n "$scope_name" && -n "$scope_root" ]] || continue
    db="$REPORT_DIR/semantic_index_${scope_name}.sqlite"
    record_command \
      "semantic-index-build:${scope_name}" \
      "$REPORT_DIR/semantic_index_build_${scope_name}.txt" \
      run_agent_canon semantic-index build \
        --root "$scope_root" \
        --db "$db"
    if [[ -n "$SEMANTIC_LLM_PROVIDER" && -n "$SEMANTIC_LLM_MODEL" ]]; then
      embed_args=(
        semantic-index embed-provider
        --root "$scope_root"
        --db "$db"
        --provider "$SEMANTIC_LLM_PROVIDER"
        --model "$SEMANTIC_LLM_MODEL"
        --dim "$SEMANTIC_LLM_DIM"
        --embedding-batch "$SEMANTIC_LLM_BATCH"
      )
      if [[ -n "$SEMANTIC_LLM_URL" ]]; then
        embed_args+=(--embedding-url "$SEMANTIC_LLM_URL")
      fi
      record_command \
        "semantic-index-embed-provider:${scope_name}" \
        "$REPORT_DIR/semantic_index_embed_provider_${scope_name}.txt" \
        run_agent_canon "${embed_args[@]}"
    fi
    record_command \
      "semantic-index-merge-candidates:${scope_name}" \
      "$REPORT_DIR/semantic_index_merge_candidates_${scope_name}.jsonl" \
      run_agent_canon semantic-index merge-candidates \
        --root "$scope_root" \
        --db "$db" \
        --min-score "$SEMANTIC_MIN_SCORE" \
        --top-k "$SEMANTIC_TOP_K" \
        --format jsonl
    record_command \
      "semantic-index-thin-docs:${scope_name}" \
      "$REPORT_DIR/semantic_index_thin_docs_${scope_name}.jsonl" \
      run_agent_canon semantic-index thin-docs \
        --root "$scope_root" \
        --db "$db" \
        --top-k "$SEMANTIC_TOP_K" \
        --format jsonl
    if [[ -n "$SEMANTIC_QUERY_FILE" ]]; then
      record_command \
        "semantic-index-search:${scope_name}" \
        "$REPORT_DIR/semantic_index_search_${scope_name}.jsonl" \
        run_agent_canon semantic-index search \
          --root "$scope_root" \
          --db "$db" \
          --query-file "$SEMANTIC_QUERY_FILE" \
          --top-k "$SEMANTIC_TOP_K" \
          --format jsonl
    fi
    eval_args=(
      semantic-index eval-output
      --merge-candidates "$REPORT_DIR/semantic_index_merge_candidates_${scope_name}.jsonl"
      --thin-docs "$REPORT_DIR/semantic_index_thin_docs_${scope_name}.jsonl"
      --report "$REPORT_DIR/semantic_index_output_eval_${scope_name}.json"
    )
    if [[ -n "$SEMANTIC_QUERY_FILE" ]]; then
      eval_args+=(--search "$REPORT_DIR/semantic_index_search_${scope_name}.jsonl")
    fi
    record_command \
      "semantic-index-output-eval:${scope_name}" \
      "$REPORT_DIR/semantic_index_output_eval_${scope_name}.txt" \
      run_agent_canon "${eval_args[@]}"
    if [[ -n "$SEMANTIC_LLM_PROVIDER" && -n "$SEMANTIC_LLM_MODEL" ]]; then
      compare_args=(
        semantic-index compare-providers
        --db "$db"
        --left-provider deterministic-dense-v1
        --left-model hash-token-char-v1
        --right-provider "$SEMANTIC_LLM_PROVIDER"
        --right-model "$SEMANTIC_LLM_MODEL"
        --right-dim "$SEMANTIC_LLM_DIM"
        --min-score "$SEMANTIC_MIN_SCORE"
        --top-k "$SEMANTIC_TOP_K"
        --report "$REPORT_DIR/semantic_index_provider_compare_${scope_name}.json"
      )
      if [[ -n "$SEMANTIC_QUERY_FILE" ]]; then
        compare_args+=(--query-file "$SEMANTIC_QUERY_FILE")
      fi
      if [[ -n "$SEMANTIC_LLM_URL" ]]; then
        compare_args+=(--right-embedding-url "$SEMANTIC_LLM_URL")
      fi
      record_command \
        "semantic-index-provider-compare:${scope_name}" \
        "$REPORT_DIR/semantic_index_provider_compare_${scope_name}.txt" \
        run_agent_canon "${compare_args[@]}"
    fi
  done < <(scope_roots)
}

run_convention() {
  record_command \
    "convention" \
    "$REPORT_DIR/convention_compliance.txt" \
    python3 "$TOOL_DIR/check_convention_compliance.py"
}

write_report() {
  {
    cat <<EOF
# Review Backlog Scan

<!--
@dependency-start
responsibility Records integrated review backlog scan output.
upstream implementation ../../tools/repository/github/review_backlog_scan.sh generates this report
upstream implementation ../../tools/analysis/code/file_surface_inventory.py generates inventory artifacts
@dependency-end
-->

- root: $ROOT_DIR
- scope_mode: $SCOPE_MODE
- report_dir: $REPORT_DIR
- nonzero_commands: $NONZERO_COMMANDS

## Artifacts

- file_inventory_json: $REPORT_DIR/file_surface_inventory.json
- file_inventory_markdown: $REPORT_DIR/file_surface_inventory.md
- semantic_index_db_pattern: $REPORT_DIR/semantic_index_<scope>.sqlite
- semantic_index_merge_candidates_pattern: $REPORT_DIR/semantic_index_merge_candidates_<scope>.jsonl
- semantic_index_thin_docs_pattern: $REPORT_DIR/semantic_index_thin_docs_<scope>.jsonl
- semantic_index_search_pattern: $REPORT_DIR/semantic_index_search_<scope>.jsonl
- semantic_index_output_eval_pattern: $REPORT_DIR/semantic_index_output_eval_<scope>.json
- semantic_index_provider_compare_pattern: $REPORT_DIR/semantic_index_provider_compare_<scope>.json
- command_status: $COMMAND_STATUS

## Command Status

| Check | Exit | Artifact |
| ----- | ---- | -------- |
EOF
    awk -F '\t' '{ printf "| %s | %s | %s |\n", $1, $2, $3 }' "$COMMAND_STATUS"
  } >"$REPORT"
}

: >"$COMMAND_STATUS"

if has_check inventory; then
  run_inventory
fi
if has_check stale; then
  run_stale_search
fi
run_scope_checks
if has_check convention; then
  run_convention
fi
if has_check semantic-index; then
  run_semantic_index
fi
write_report

echo "REVIEW_BACKLOG_SCAN=pass"
echo "REVIEW_BACKLOG_SCAN_SCOPE=$SCOPE_MODE"
echo "REVIEW_BACKLOG_SCAN_REPORT=$REPORT"
echo "REVIEW_BACKLOG_SCAN_NONZERO_COMMANDS=$NONZERO_COMMANDS"

if [[ "$FAIL_ON_FINDINGS" -eq 1 && "$NONZERO_COMMANDS" -ne 0 ]]; then
  exit 1
fi
