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
SCOPE_MODE="submodule-aware"
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

usage() {
  cat <<'EOF'
Usage:
  review_backlog_scan.sh [--root DIR] [--report-dir DIR]
                         [--submodule-aware|--root-only|--agentcanon-only]
                         [--semantic-query-file FILE]
                         [--semantic-top-k N] [--semantic-min-score SCORE]
                         [--semantic-llm-provider NAME --semantic-llm-model NAME]
                         [--semantic-embedding-url URL]
                         [--check NAME ...] [--fail-on-findings]

Runs integrated review scans and writes JSON/Markdown/log artifacts under REPORT_DIR.
Default scope is --submodule-aware. Default checks are all checks.

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
    --submodule-aware)
      SCOPE_MODE="submodule-aware"
      shift
      ;;
    --root-only)
      SCOPE_MODE="root-only"
      shift
      ;;
    --agentcanon-only)
      SCOPE_MODE="agentcanon-only"
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

ROOT_DIR="$(realpath -m "$ROOT_DIR")"
if [[ -z "$REPORT_DIR" ]]; then
  REPORT_DIR="$ROOT_DIR/reports/agents/review-backlog-scan"
fi
REPORT_DIR="$(realpath -m "$REPORT_DIR")"
if [[ -n "$SEMANTIC_QUERY_FILE" ]]; then
  SEMANTIC_QUERY_FILE="$(realpath -m "$SEMANTIC_QUERY_FILE")"
fi
mkdir -p "$REPORT_DIR"

TOOL_DIR="$ROOT_DIR/tools/agent_tools"
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
  case "$SCOPE_MODE" in
    root-only) printf '%s\n' "--root-only" ;;
    agentcanon-only) printf '%s\n' "--agentcanon-only" ;;
    *) printf '%s\n' "--submodule-aware" ;;
  esac
}

scope_roots() {
  local canon_root="$ROOT_DIR/vendor/agent-canon"
  case "$SCOPE_MODE" in
    root-only)
      printf 'root\t%s\n' "$ROOT_DIR"
      ;;
    agentcanon-only)
      if [[ -d "$canon_root" ]]; then
        printf 'agentcanon\t%s\n' "$canon_root"
      else
        printf 'agentcanon\t%s\n' "$ROOT_DIR"
      fi
      ;;
    *)
      printf 'root\t%s\n' "$ROOT_DIR"
      if [[ -d "$canon_root" ]]; then
        printf 'agentcanon\t%s\n' "$canon_root"
      fi
      ;;
  esac
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

run_agent_canon() {
  if command -v cargo >/dev/null 2>&1 && [[ -f "$AGENT_CANON_SOURCE_ROOT/rust/agent-canon/Cargo.toml" ]]; then
    CARGO_TARGET_DIR="${AGENT_CANON_REVIEW_SCAN_TARGET_DIR:-/tmp/agent-canon-review-scan-target}" \
      cargo run --quiet --manifest-path "$AGENT_CANON_SOURCE_ROOT/rust/agent-canon/Cargo.toml" -- "$@"
    return
  fi
  if command -v cargo >/dev/null 2>&1 && [[ -f "$ROOT_DIR/rust/agent-canon/Cargo.toml" ]]; then
    CARGO_TARGET_DIR="${AGENT_CANON_REVIEW_SCAN_TARGET_DIR:-/tmp/agent-canon-review-scan-target}" \
      cargo run --quiet --manifest-path "$ROOT_DIR/rust/agent-canon/Cargo.toml" -- "$@"
    return
  fi
  if command -v cargo >/dev/null 2>&1 && [[ -f "$ROOT_DIR/vendor/agent-canon/rust/agent-canon/Cargo.toml" ]]; then
    CARGO_TARGET_DIR="${AGENT_CANON_REVIEW_SCAN_TARGET_DIR:-/tmp/agent-canon-review-scan-target}" \
      cargo run --quiet --manifest-path "$ROOT_DIR/vendor/agent-canon/rust/agent-canon/Cargo.toml" -- "$@"
    return
  fi
  if command -v agent-canon >/dev/null 2>&1; then
    if agent-canon semantic-index help 2>/dev/null \
      | grep -Eq 'embed-provider.*context-pack.*compare-providers.*eval-output|context-pack.*embed-provider.*compare-providers.*eval-output'; then
      agent-canon "$@"
      return
    fi
  fi
  if [[ -x "$AGENT_CANON_SOURCE_ROOT/rust/agent-canon/target/debug/agent-canon" ]]; then
    if "$AGENT_CANON_SOURCE_ROOT/rust/agent-canon/target/debug/agent-canon" semantic-index help 2>/dev/null \
      | grep -Eq 'embed-provider.*context-pack.*compare-providers.*eval-output|context-pack.*embed-provider.*compare-providers.*eval-output'; then
      "$AGENT_CANON_SOURCE_ROOT/rust/agent-canon/target/debug/agent-canon" "$@"
      return
    fi
  fi
  if [[ -x "$ROOT_DIR/rust/agent-canon/target/debug/agent-canon" ]]; then
    if "$ROOT_DIR/rust/agent-canon/target/debug/agent-canon" semantic-index help 2>/dev/null \
      | grep -Eq 'embed-provider.*context-pack.*compare-providers.*eval-output|context-pack.*embed-provider.*compare-providers.*eval-output'; then
      "$ROOT_DIR/rust/agent-canon/target/debug/agent-canon" "$@"
      return
    fi
  fi
  if [[ -x "$ROOT_DIR/vendor/agent-canon/rust/agent-canon/target/debug/agent-canon" ]]; then
    if "$ROOT_DIR/vendor/agent-canon/rust/agent-canon/target/debug/agent-canon" semantic-index help 2>/dev/null \
      | grep -Eq 'embed-provider.*context-pack.*compare-providers.*eval-output|context-pack.*embed-provider.*compare-providers.*eval-output'; then
      "$ROOT_DIR/vendor/agent-canon/rust/agent-canon/target/debug/agent-canon" "$@"
      return
    fi
  fi
  echo "agent-canon CLI unavailable for ROOT_DIR=$ROOT_DIR" >&2
  return 127
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
    if [[ "$scope_name" == "root" ]]; then
      excludes+=(--exclude vendor)
    fi
    if has_check code-dependencies; then
      record_command \
        "code-dependencies:${scope_name}" \
        "$REPORT_DIR/code_dependencies_${scope_name}.txt" \
        bash "$TOOL_DIR/scan_code_dependencies.sh" --root "$scope_root"
    fi
    if has_check dependency-review; then
      record_command \
        "dependency-review:${scope_name}" \
        "$REPORT_DIR/dependency_review_${scope_name}.txt" \
        bash "$TOOL_DIR/run_repo_dependency_review.sh" --root "$scope_root" --fail-missing
    fi
    if has_check oop; then
      record_command \
        "oop-python:${scope_name}" \
        "$REPORT_DIR/oop_python_readability_${scope_name}.md" \
        python3 "$ROOT_DIR/tools/oop/python/readability.py" \
          --root "$scope_root" \
          --format markdown \
          --include-snippets \
          --min-score 0 \
          --exclude .git \
          "${excludes[@]}" \
          "${paths[@]}"
      record_command \
        "oop-cpp:${scope_name}" \
        "$REPORT_DIR/oop_cpp_readability_${scope_name}.md" \
        python3 "$ROOT_DIR/tools/oop/cpp/readability.py" \
          --root "$scope_root" \
          --format markdown \
          --include-snippets \
          --min-score 0 \
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
upstream implementation ../../../../vendor/agent-canon/tools/agent_tools/review_backlog_scan.sh generates this report
upstream implementation ../../../../vendor/agent-canon/tools/agent_tools/file_surface_inventory.py generates inventory artifacts
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
