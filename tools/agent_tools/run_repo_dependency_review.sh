#!/usr/bin/env bash
# @dependency-start
# contract tool
# responsibility Runs source-owned repo dependency review and optional persisted graph preparation.
# upstream design ../../documents/design/dependency-manifest-design.md dependency review policy
# upstream design ../../agents/canonical/CODEX_WORKFLOW.md closeout requires dependency evidence
# upstream design ../../templates/agents/closeout_gate.md closeout dependency evidence gate
# upstream design ../../.github/PULL_REQUEST_TEMPLATE.md standalone PR dependency checklist
# upstream design ../../.github/PULL_REQUEST_TEMPLATE/agent_canon.md template PR dependency checklist
# upstream design ../../templates/documents/github/pull-request/agent_canon.md canonical template-side AgentCanon PR checklist
# upstream implementation ./scan_dependency_headers.sh scans repo-wide manifest coverage
# upstream implementation ./check_dependency_header_format.sh validates repo-wide manifest syntax
# upstream implementation ./check_dependency_graph.sh validates source-derived dependency relations
# upstream implementation ./check_design_doc_claims.py validates design claims against dependency evidence
# downstream implementation ../../tools/ci/check_agent_canon_pr.sh runs strict dependency review
# downstream implementation ../../tests/agent_tools/test_dependency_manifest_tools.py verifies wrapper behavior
# @dependency-end
set -euo pipefail

ROOT_DIR="$(git -C "$PWD" rev-parse --show-toplevel 2>/dev/null || pwd)"
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
REVIEW_PARENT_ROOT=""
# shellcheck source=../lib/repo_paths.sh
source "${script_dir}/../lib/repo_paths.sh"

parent_temp_base() {
  REVIEW_PARENT_ROOT="$(realpath -e "${AGENT_CANON_PARENT_ROOT:-$ROOT_DIR}")" || {
    echo "REPO_DEPENDENCY_REVIEW=fail reason=parent_root_missing" >&2
    return 2
  }
  ROOT_PHYSICAL="$(realpath -e "$ROOT_DIR")" || {
    echo "REPO_DEPENDENCY_REVIEW=fail reason=root_missing" >&2
    return 2
  }
  case "$ROOT_PHYSICAL" in
    "$REVIEW_PARENT_ROOT"|"$REVIEW_PARENT_ROOT"/*) ;;
    *)
      echo "REPO_DEPENDENCY_REVIEW=fail reason=parent_root_not_ancestor" >&2
      return 2
      ;;
  esac
  python3 "${script_dir}/parent_root_side_effects.py" temp-dir \
    --root "$REVIEW_PARENT_ROOT" \
    --candidate "$REVIEW_PARENT_ROOT/.agent-canon/tmp/dependency-review" \
    --prefix review --purpose dependency-review-temp
}
CHECK_BIDIRECTIONAL=0
CYCLE_REPORT_ONLY=0
FAIL_MISSING=0
ALLOW_FRONTMATTER=0
EXPLAIN_MISSING=0
LIST_CHANGED_DEPENDENCIES=0
REPORT_DIR="${AGENT_RUN_REPORT_DIR:-}"
GRAPH_TSV_OUTPUT=""
SEARCH_HITS_FILE=""
CHANGED_PATH_PACKET=""
TRUSTED_BASE_SHA=""
HEADER_SCAN_ONLY=0
CHECK_DESIGN_DOC_CLAIMS=0
ENSURE_GRAPH_ONLY=0
declare -a DESIGN_DOC_CLAIM_PATHS=()

usage() {
  cat <<'EOF'
Usage:
  run_repo_dependency_review.sh [--root DIR] [--check-bidirectional] [--cycle-report-only] [--fail-missing] [--allow-frontmatter] [--explain-missing] [--changed-path-packet FILE] [--trusted-base-sha SHA] [--header-scan-only] [--ensure-graph] [--list-changed-dependencies] [--report-dir DIR] [--graph-tsv PATH] [--search-hits-file PATH] [--check-design-doc-claims] [--design-doc-claim-path PATH]

Runs dependency manifest review against all tracked, checkable text files in the repo.
This is intended for checkpoint and final review, not just changed-file closeout.
Missing manifests are report-only by default until the repository-wide migration is complete.
With --list-changed-dependencies, the source graph checker also prints every dependency
edge declared by, or pointing at, each changed file.
When --report-dir is set, a stable dependency_graph.tsv artifact is generated
directly from dependency headers. With --search-hits-file, text-search hit paths are
expanded into dependency edit-scope candidates and saved beside the graph when
--report-dir is set. Without --search-hits-file, the report directory still
receives changed-file dependency edit-scope evidence.
With --cycle-report-only, dependency cycles stay visible but do not block the
wrapper. Use this only with a durable source-derived graph report artifact.
With --changed-path-packet, selector-owned trusted base/head path evidence is
passed to the canonical scan; unchanged missing headers remain baseline evidence.
With --trusted-base-sha, the packet base is bound to an independent caller authority.
With --header-scan-only, source relation/cycle validation and graph projections are
skipped while the strict canonical header scan and format check still run.
With --ensure-graph, the opt-in persisted graph status/build operation runs once
and exits before source-owned dependency-header review.
With --check-design-doc-claims, changed design documents are compared with
dependency header evidence and implementation-backed claim tokens. Repeat
--design-doc-claim-path to check explicit design documents instead of changed
scope.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --root)
      ROOT_DIR="$2"
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
    --changed-path-packet)
      [[ $# -ge 2 ]] || { echo "REPO_DEPENDENCY_REVIEW=fail reason=changed_path_packet_argument_missing"; exit 2; }
      CHANGED_PATH_PACKET="$2"
      shift 2
      ;;
    --trusted-base-sha)
      [[ $# -ge 2 ]] || { echo "REPO_DEPENDENCY_REVIEW=fail reason=trusted_base_argument_missing"; exit 2; }
      TRUSTED_BASE_SHA="$2"
      shift 2
      ;;
    --header-scan-only)
      HEADER_SCAN_ONLY=1
      shift
      ;;
    --ensure-graph)
      ENSURE_GRAPH_ONLY=1
      shift
      ;;
    --list-changed-dependencies)
      LIST_CHANGED_DEPENDENCIES=1
      shift
      ;;
    --report-dir)
      REPORT_DIR="$2"
      shift 2
      ;;
    --graph-tsv)
      GRAPH_TSV_OUTPUT="$2"
      shift 2
      ;;
    --search-hits-file)
      SEARCH_HITS_FILE="$2"
      shift 2
      ;;
    --check-design-doc-claims)
      CHECK_DESIGN_DOC_CLAIMS=1
      shift
      ;;
    --design-doc-claim-path)
      CHECK_DESIGN_DOC_CLAIMS=1
      DESIGN_DOC_CLAIM_PATHS+=("$2")
      shift 2
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

ROOT_DIR="$(realpath -e "$ROOT_DIR")" || {
  echo "REPO_DEPENDENCY_REVIEW=fail reason=root_missing"
  exit 2
}
SCRIPT_TOOLS_ROOT="$(dirname "$(realpath -m "$script_dir")")"
cd "$ROOT_DIR"

if [[ "$HEADER_SCAN_ONLY" -eq 1 && "$ENSURE_GRAPH_ONLY" -eq 1 ]]; then
  echo "REPO_DEPENDENCY_REVIEW=fail reason=header_scan_and_ensure_graph_are_mutually_exclusive"
  exit 2
fi
if [[ "$HEADER_SCAN_ONLY" -eq 1 && ( -z "$CHANGED_PATH_PACKET" || -z "$TRUSTED_BASE_SHA" ) ]]; then
  echo "REPO_DEPENDENCY_REVIEW=fail reason=header_scan_trusted_packet_required"
  exit 2
fi

SCRIPT_TOOLS_ROOT="$(realpath -m "$SCRIPT_TOOLS_ROOT")"

if [[ "$HEADER_SCAN_ONLY" -eq 0 ]]; then
  CANON_TOOLS_ROOT="$(agent_canon_source_tools_root "$ROOT_DIR")" || {
    echo "canonical AgentCanon source tools root is unavailable for root: $ROOT_DIR" >&2
    exit 1
  }
  CANON_TOOLS_ROOT="$(realpath -m "$CANON_TOOLS_ROOT")"
  SCAN_DEPENDENCY_HEADERS="${CANON_TOOLS_ROOT}/agent_tools/scan_dependency_headers.sh"
  CHECK_DEPENDENCY_HEADER_FORMAT="${CANON_TOOLS_ROOT}/agent_tools/check_dependency_header_format.sh"
  CHECK_DEPENDENCY_GRAPH="${CANON_TOOLS_ROOT}/agent_tools/check_dependency_graph.sh"
  CHECK_DESIGN_DOC_CLAIMS_TOOL="${CANON_TOOLS_ROOT}/agent_tools/check_design_doc_claims.py"
  GRAPH_CLI="${CANON_TOOLS_ROOT}/bin/agent-canon"
  WORKFLOW_MONITOR="${CANON_TOOLS_ROOT}/agent_tools/workflow_monitor.py"
else
  SCAN_DEPENDENCY_HEADERS="${SCRIPT_TOOLS_ROOT}/agent_tools/scan_dependency_headers.sh"
  CHECK_DEPENDENCY_HEADER_FORMAT="${SCRIPT_TOOLS_ROOT}/agent_tools/check_dependency_header_format.sh"
  WORKFLOW_MONITOR="${SCRIPT_TOOLS_ROOT}/agent_tools/workflow_monitor.py"
  CHECK_DEPENDENCY_GRAPH="${SCRIPT_TOOLS_ROOT}/agent_tools/check_dependency_graph.sh"
  CHECK_DESIGN_DOC_CLAIMS_TOOL="${SCRIPT_TOOLS_ROOT}/agent_tools/check_design_doc_claims.py"
fi

if [[ "$ENSURE_GRAPH_ONLY" -eq 1 ]]; then
  if [[ ! -x "$GRAPH_CLI" ]]; then
    echo "canonical graph executable is missing for root: $ROOT_DIR" >&2
    exit 1
  fi

  tmp_base="$(parent_temp_base)"
  status_file="$(mktemp "$tmp_base/status.XXXXXX")"
  cleanup_review_tmp() {
    local primary_status=$?
    local cleanup_status=0
    trap - EXIT
    python3 "${script_dir}/parent_root_side_effects.py" remove-tree \
      --root "$REVIEW_PARENT_ROOT" --candidate "$tmp_base" \
      --purpose dependency-review-temp >/dev/null || cleanup_status=$?
    if [[ "$primary_status" -ne 0 ]]; then
      exit "$primary_status"
    fi
    exit "$cleanup_status"
  }
  trap cleanup_review_tmp EXIT

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
  elif [[ "$status_binding" == "$source_changed_binding" ]]; then
    echo "GRAPH_REBUILD=required status=stale reason=source_changed probe_reason=source_changed"
    set +e
    "$GRAPH_CLI" graph build --root "$ROOT_DIR" --profile default --format json
    build_exit=$?
    set -e
    if [[ "$build_exit" -ne 0 && "$build_exit" -ne 1 ]]; then
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
    echo "REPO_DEPENDENCY_REVIEW=fail"
    cat "$status_file"
    exit 1
  fi
  echo "GRAPH_ENSURE=pass status=fresh"
  exit 0
fi

mapfile -t checkable_paths < <(
  git ls-files | awk '
    /^reports\/agents\// { next }
    /^reports\/dependency-review\// { next }
    /\.(bash|cfg|css|h|hpp|html|c|cc|cpp|json|md|py|rst|sh|toml|txt|yaml|yml|zsh)$/ { print }
  '
)

echo "REPO_DEPENDENCY_REVIEW_PATHS=${#checkable_paths[@]}"

scan_args=("$SCAN_DEPENDENCY_HEADERS")
format_args=("$CHECK_DEPENDENCY_HEADER_FORMAT")
if [[ -n "$CHANGED_PATH_PACKET" ]]; then
  scan_args+=(--changed-path-packet "$CHANGED_PATH_PACKET")
  scan_args+=(--trusted-base-sha "$TRUSTED_BASE_SHA")
fi
if [[ "$FAIL_MISSING" -eq 1 ]]; then
  scan_args+=(--fail-missing)
  if [[ -z "$CHANGED_PATH_PACKET" ]]; then
    format_args+=(--require-header)
  fi
fi
if [[ "$ALLOW_FRONTMATTER" -eq 1 ]]; then
  scan_args+=(--allow-frontmatter)
  format_args+=(--allow-frontmatter)
fi
if [[ "$EXPLAIN_MISSING" -eq 1 ]]; then
  scan_args+=(--explain-missing)
fi

if [[ -n "$CHANGED_PATH_PACKET" ]]; then
  bash "${scan_args[@]}"
else
  bash "${scan_args[@]}" "${checkable_paths[@]}"
fi
bash "${format_args[@]}" "${checkable_paths[@]}"

if [[ "$HEADER_SCAN_ONLY" -eq 1 ]]; then
  echo "REPO_DEPENDENCY_REVIEW=pass"
  if [[ -n "$REPORT_DIR" ]]; then
    python3 "$WORKFLOW_MONITOR" \
      --report-dir "$REPORT_DIR" \
      --signal "repo_dependency_review=pass header_scan_only=yes paths=${#checkable_paths[@]} fail_missing=${FAIL_MISSING} changed_path_packet=${CHANGED_PATH_PACKET:-none}" \
      --intervention "run_repo_dependency_review.sh recorded header scan pass"
  fi
  exit 0
fi

if [[ -n "$REPORT_DIR" ]]; then
  if [[ -n "${AGENT_CANON_PARENT_ROOT:-}" ]]; then
    parent_root_real="$(realpath -m "$AGENT_CANON_PARENT_ROOT")"
    report_real="$(realpath -m "$REPORT_DIR")"
    case "$report_real" in
      "$parent_root_real"|"$parent_root_real"/*) ;;
      *) echo "REPO_DEPENDENCY_REVIEW=fail reason=report_dir_outside_parent"; exit 2 ;;
    esac
  fi
  mkdir -p "$REPORT_DIR"
fi
if [[ -z "$GRAPH_TSV_OUTPUT" && -n "$REPORT_DIR" ]]; then
  GRAPH_TSV_OUTPUT="$REPORT_DIR/dependency_graph.tsv"
fi

graph_args=("$CHECK_DEPENDENCY_GRAPH")
if [[ "$CHECK_BIDIRECTIONAL" -eq 1 ]]; then
  graph_args+=(--check-bidirectional)
fi
if [[ "$CYCLE_REPORT_ONLY" -eq 1 ]]; then
  graph_args+=(--cycle-report-only)
fi
if [[ "$ALLOW_FRONTMATTER" -eq 1 ]]; then
  graph_args+=(--allow-frontmatter)
fi
if [[ -n "$GRAPH_TSV_OUTPUT" ]]; then
  graph_args+=(--graph-tsv "$GRAPH_TSV_OUTPUT")
fi
bash "${graph_args[@]}" "${checkable_paths[@]}"

if [[ "$LIST_CHANGED_DEPENDENCIES" -eq 1 ]]; then
  related_args=("$CHECK_DEPENDENCY_GRAPH" --list-related --focus-changed)
  if [[ "$CYCLE_REPORT_ONLY" -eq 1 ]]; then
    related_args+=(--cycle-report-only)
  fi
  if [[ "$ALLOW_FRONTMATTER" -eq 1 ]]; then
    related_args+=(--allow-frontmatter)
  fi
  bash "${related_args[@]}" "${checkable_paths[@]}"
fi

if [[ "$CHECK_DESIGN_DOC_CLAIMS" -eq 1 ]]; then
  design_claim_args=("$CHECK_DESIGN_DOC_CLAIMS_TOOL" --root "$ROOT_DIR")
  if [[ ${#DESIGN_DOC_CLAIM_PATHS[@]} -gt 0 ]]; then
    design_claim_args+=("${DESIGN_DOC_CLAIM_PATHS[@]}")
  else
    design_claim_args+=(--changed)
  fi
  python3 "${design_claim_args[@]}"
fi

if [[ -n "$SEARCH_HITS_FILE" ]]; then
  edit_scope_args=("$CHECK_DEPENDENCY_GRAPH" --search-hits-file "$SEARCH_HITS_FILE")
  if [[ "$CYCLE_REPORT_ONLY" -eq 1 ]]; then
    edit_scope_args+=(--cycle-report-only)
  fi
  if [[ "$ALLOW_FRONTMATTER" -eq 1 ]]; then
    edit_scope_args+=(--allow-frontmatter)
  fi
  if [[ -n "$REPORT_DIR" ]]; then
    bash "${edit_scope_args[@]}" "${checkable_paths[@]}" | tee "$REPORT_DIR/dependency_edit_scope.txt"
  else
    bash "${edit_scope_args[@]}" "${checkable_paths[@]}"
  fi
elif [[ -n "$REPORT_DIR" ]]; then
  edit_scope_args=("$CHECK_DEPENDENCY_GRAPH" --edit-scope-changed)
  if [[ "$CYCLE_REPORT_ONLY" -eq 1 ]]; then
    edit_scope_args+=(--cycle-report-only)
  fi
  if [[ "$ALLOW_FRONTMATTER" -eq 1 ]]; then
    edit_scope_args+=(--allow-frontmatter)
  fi
  bash "${edit_scope_args[@]}" "${checkable_paths[@]}" | tee "$REPORT_DIR/dependency_edit_scope.txt"
fi

echo "REPO_DEPENDENCY_REVIEW=pass"

if [[ -n "$REPORT_DIR" ]]; then
  python3 "$WORKFLOW_MONITOR" \
    --report-dir "$REPORT_DIR" \
    --signal "repo_dependency_review=pass paths=${#checkable_paths[@]} check_bidirectional=${CHECK_BIDIRECTIONAL} fail_missing=${FAIL_MISSING} changed_path_packet=${CHANGED_PATH_PACKET:-none}" \
    --intervention "run_repo_dependency_review.sh recorded dependency review pass"
fi
