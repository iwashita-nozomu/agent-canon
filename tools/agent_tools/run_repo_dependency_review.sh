#!/usr/bin/env bash
# @dependency-start
# contract tool
# responsibility Runs repo dependency review agent workflow automation.
# upstream design ../../documents/design/dependency-manifest-design.md dependency review policy
# upstream design ../../agents/canonical/CODEX_WORKFLOW.md closeout requires dependency evidence
# upstream design ../../templates/agents/closeout_gate.md closeout dependency evidence gate
# upstream design ../../.github/PULL_REQUEST_TEMPLATE.md standalone PR dependency checklist
# upstream design ../../.github/PULL_REQUEST_TEMPLATE/agent_canon.md template PR dependency checklist
# upstream design ../../templates/documents/github/pull-request/agent_canon.md canonical template-side AgentCanon PR checklist
# upstream implementation ./scan_dependency_headers.sh scans repo-wide manifest coverage
# upstream implementation ./check_dependency_header_format.sh validates repo-wide manifest syntax
# upstream implementation ./check_dependency_graph.sh validates repo-wide dependency graph
# upstream implementation ./check_design_doc_claims.py validates design claims against dependency evidence
# upstream implementation ../lib/repo_paths.sh separates target data from analyzer tools
# downstream implementation ../../tools/ci/check_agent_canon_pr.sh runs strict dependency review
# downstream implementation ../../tests/agent_tools/test_dependency_manifest_tools.py verifies wrapper behavior
# @dependency-end
set -euo pipefail

INVOCATION_SCRIPT="$(realpath -e "${BASH_SOURCE[0]}" 2>/dev/null || true)"
BOUNDARY_SCRIPT="$(dirname "$INVOCATION_SCRIPT")/parent_root_side_effects.py"
if [[ -z "${AGENT_CANON_SIDE_EFFECT_HANDOFF:-}" ]]; then
  if [[ -z "$INVOCATION_SCRIPT" || ! -f "$INVOCATION_SCRIPT" ]]; then
    echo "REPO_DEPENDENCY_REVIEW=fail reason=invocation_script_missing" >&2
    exit 2
  fi
  exec python3 "$BOUNDARY_SCRIPT" public-exec \
    --invocation-script "$INVOCATION_SCRIPT" \
    --purpose dependency-review \
    -- bash "$INVOCATION_SCRIPT" "$@"
fi

ROOT_DIR="$(git -C "$PWD" rev-parse --show-toplevel 2>/dev/null || pwd)"
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
REVIEW_PARENT_ROOT=""
# shellcheck source=../lib/repo_paths.sh
source "${script_dir}/../lib/repo_paths.sh"

resolve_review_parent_root() {
  if [[ -n "${AGENT_CANON_SIDE_EFFECT_PARENT_ROOT:-}" && -z "${AGENT_CANON_SIDE_EFFECT_HANDOFF:-}" ]]; then
    echo "REPO_DEPENDENCY_REVIEW=fail reason=side_effect_session_missing" >&2
    return 2
  fi
  REVIEW_PARENT_ROOT="$(realpath -e "${AGENT_CANON_SIDE_EFFECT_PARENT_ROOT:-$ROOT_DIR}")" || {
    echo "REPO_DEPENDENCY_REVIEW=fail reason=parent_root_missing" >&2
    return 2
  }
}

parent_temp_base() {
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
ANALYZER_TOOLS_ROOT_OVERRIDE=""
declare -a ANALYZER_REQUIRED_ENTRIES=()
declare -a DESIGN_DOC_CLAIM_PATHS=()

usage() {
  cat <<'EOF'
Usage:
  run_repo_dependency_review.sh [--root DIR] [--analyzer-tools-root DIR] [--check-bidirectional] [--cycle-report-only] [--fail-missing] [--allow-frontmatter] [--explain-missing] [--changed-path-packet FILE] [--trusted-base-sha SHA] [--header-scan-only] [--ensure-graph] [--list-changed-dependencies] [--report-dir DIR] [--graph-tsv PATH] [--search-hits-file PATH] [--check-design-doc-claims] [--design-doc-claim-path PATH]

Runs dependency manifest review against all tracked, checkable text files in the repo.
This is intended for checkpoint and final review, not just changed-file closeout.
Missing manifests are report-only by default until the repository-wide migration is complete.
With --list-changed-dependencies, the graph checker also prints every dependency
edge declared by, or pointing at, each changed file.
When --report-dir is set, a stable dependency_graph.tsv artifact is generated
from dependency headers. With --search-hits-file, text-search hit paths are
expanded into dependency edit-scope candidates and saved beside the graph when
--report-dir is set. Without --search-hits-file, the report directory still
receives changed-file dependency edit-scope evidence.
With --cycle-report-only, dependency cycles stay visible but do not block the
wrapper. Use this only with a durable graph report artifact.
With --changed-path-packet, selector-owned trusted base/head path evidence is
passed to the canonical scan; unchanged missing headers remain baseline evidence.
With --trusted-base-sha, the packet base is bound to an independent caller authority.
With --header-scan-only, graph status/query and graph projections are skipped while
the strict canonical header scan and format check still run.
With --ensure-graph, the canonical graph status/build/readback operation runs once
and exits before dependency-header review.
With --analyzer-tools-root, the physical analyzer tools tree is selected explicitly;
otherwise AGENT_CANON_ANALYZER_TOOLS_ROOT or the invocation-source tools tree wins.
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
    --analyzer-tools-root)
      [[ $# -ge 2 ]] || { echo "REPO_DEPENDENCY_REVIEW=fail reason=analyzer_tools_root_argument_missing"; exit 2; }
      ANALYZER_TOOLS_ROOT_OVERRIDE="$2"
      shift 2
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
if [[ -n "$INVOCATION_SCRIPT" ]]; then
  SCRIPT_TOOLS_ROOT="$(realpath -e "$(dirname "$INVOCATION_SCRIPT")/..")"
else
  SCRIPT_TOOLS_ROOT="$(realpath -e "$script_dir/..")"
fi
if [[ "$HEADER_SCAN_ONLY" -eq 1 && ( -z "$CHANGED_PATH_PACKET" || -z "$TRUSTED_BASE_SHA" ) ]]; then
  echo "REPO_DEPENDENCY_REVIEW=fail reason=header_scan_trusted_packet_required"
  exit 2
fi

SCRIPT_TOOLS_ROOT="$(realpath -e "$SCRIPT_TOOLS_ROOT")"
export PYTHONDONTWRITEBYTECODE=1

if [[ "$HEADER_SCAN_ONLY" -eq 0 ]]; then
  # Authenticate the side-effect parent once.  Analyzer source selection is
  # independent from target repository identity and is validated below.
  resolve_review_parent_root
  tmp_base="$(parent_temp_base)"
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

  if [[ "$ENSURE_GRAPH_ONLY" -eq 1 ]]; then
    ANALYZER_REQUIRED_ENTRIES=(
      "agent_tools/check_dependency_graph.sh"
      "bin/agent-canon"
    )
  else
    ANALYZER_REQUIRED_ENTRIES=(
      "agent_tools/scan_dependency_headers.sh"
      "agent_tools/check_dependency_header_format.sh"
      "agent_tools/check_dependency_graph.sh"
      "bin/agent-canon"
    )
    if [[ "$CHECK_DESIGN_DOC_CLAIMS" -eq 1 ]]; then
      ANALYZER_REQUIRED_ENTRIES+=("agent_tools/check_design_doc_claims.py")
    fi
    if [[ -n "$REPORT_DIR" ]]; then
      ANALYZER_REQUIRED_ENTRIES+=("agent_tools/workflow_monitor.py")
    fi
  fi
else
  # Header-only mode still resolves analyzer source identity, while remaining
  # independent of graph readiness and graph-specific side effects.
  if [[ -n "$ANALYZER_TOOLS_ROOT_OVERRIDE" \
    || -n "${AGENT_CANON_ANALYZER_TOOLS_ROOT:-}" \
    || -n "$REPORT_DIR" ]]; then
    resolve_review_parent_root
  fi
  ANALYZER_REQUIRED_ENTRIES=(
    "agent_tools/scan_dependency_headers.sh"
    "agent_tools/check_dependency_header_format.sh"
  )
  if [[ -n "$REPORT_DIR" ]]; then
    ANALYZER_REQUIRED_ENTRIES+=("agent_tools/workflow_monitor.py")
  fi
fi

ANALYZER_PHYSICAL_DEFAULT=0
if [[ -z "$ANALYZER_TOOLS_ROOT_OVERRIDE" \
  && -z "${AGENT_CANON_ANALYZER_TOOLS_ROOT:-}" ]]; then
  ANALYZER_PHYSICAL_DEFAULT=1
fi
ANALYZER_TOOLS_ROOT="$(agent_canon_analyzer_tools_root \
  "$INVOCATION_SCRIPT" "$ANALYZER_TOOLS_ROOT_OVERRIDE" "$REVIEW_PARENT_ROOT" \
  "$ANALYZER_PHYSICAL_DEFAULT" "${ANALYZER_REQUIRED_ENTRIES[@]}")" || {
  echo "REPO_DEPENDENCY_REVIEW=fail reason=analyzer_tools_root_invalid" >&2
  exit 2
}
SCAN_DEPENDENCY_HEADERS="${ANALYZER_TOOLS_ROOT}/agent_tools/scan_dependency_headers.sh"
CHECK_DEPENDENCY_HEADER_FORMAT="${ANALYZER_TOOLS_ROOT}/agent_tools/check_dependency_header_format.sh"
CHECK_DEPENDENCY_GRAPH="${ANALYZER_TOOLS_ROOT}/agent_tools/check_dependency_graph.sh"
CHECK_DESIGN_DOC_CLAIMS_TOOL="${ANALYZER_TOOLS_ROOT}/agent_tools/check_design_doc_claims.py"
WORKFLOW_MONITOR="${ANALYZER_TOOLS_ROOT}/agent_tools/workflow_monitor.py"
export AGENT_CANON_ANALYZER_TOOLS_ROOT_PHYSICAL_DEFAULT="$ANALYZER_PHYSICAL_DEFAULT"

if [[ "$ENSURE_GRAPH_ONLY" -eq 1 ]]; then
  bash "$CHECK_DEPENDENCY_GRAPH" \
    --root "$ROOT_DIR" \
    --ensure-graph \
    --analyzer-tools-root "$ANALYZER_TOOLS_ROOT"
  exit $?
fi

if [[ -n "$REPORT_DIR" ]]; then
  parent_root_real="$REVIEW_PARENT_ROOT"
  report_real="$(realpath -m "$REPORT_DIR")"
  case "$report_real" in
    "$parent_root_real"|"$parent_root_real"/*) ;;
    *) echo "REPO_DEPENDENCY_REVIEW=fail reason=report_dir_outside_parent"; exit 2 ;;
  esac
  mkdir -p "$REPORT_DIR"
fi

mapfile -t checkable_paths < <(
  git -C "$ROOT_DIR" ls-files | awk '
    /^reports\/agents\// { next }
    /^reports\/dependency-review\// { next }
    /\.(bash|cfg|css|h|hpp|html|c|cc|cpp|json|md|py|rst|sh|toml|txt|yaml|yml|zsh)$/ { print }
  '
)

echo "REPO_DEPENDENCY_REVIEW_PATHS=${#checkable_paths[@]}"

scan_args=("$SCAN_DEPENDENCY_HEADERS")
format_args=("$CHECK_DEPENDENCY_HEADER_FORMAT")
scan_args+=(--root "$ROOT_DIR")
format_args+=(--root "$ROOT_DIR")
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

if [[ -z "$GRAPH_TSV_OUTPUT" && -n "$REPORT_DIR" ]]; then
  GRAPH_TSV_OUTPUT="$REPORT_DIR/dependency_graph.tsv"
fi

graph_args=("$CHECK_DEPENDENCY_GRAPH" --root "$ROOT_DIR" --analyzer-tools-root "$ANALYZER_TOOLS_ROOT")
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
if [[ "$LIST_CHANGED_DEPENDENCIES" -eq 1 ]]; then
  graph_args+=(--list-related --focus-changed)
fi
if [[ -n "$SEARCH_HITS_FILE" ]]; then
  graph_args+=(--search-hits-file "$SEARCH_HITS_FILE")
elif [[ -n "$REPORT_DIR" ]]; then
  graph_args+=(--edit-scope-changed)
fi

if [[ -n "$REPORT_DIR" ]]; then
  bash "${graph_args[@]}" "${checkable_paths[@]}" | tee "$REPORT_DIR/dependency_edit_scope.txt"
else
  bash "${graph_args[@]}" "${checkable_paths[@]}"
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

echo "REPO_DEPENDENCY_REVIEW=pass"

if [[ -n "$REPORT_DIR" ]]; then
  python3 "$WORKFLOW_MONITOR" \
    --report-dir "$REPORT_DIR" \
    --signal "repo_dependency_review=pass paths=${#checkable_paths[@]} check_bidirectional=${CHECK_BIDIRECTIONAL} fail_missing=${FAIL_MISSING} changed_path_packet=${CHANGED_PATH_PACKET:-none}" \
    --intervention "run_repo_dependency_review.sh recorded dependency review pass"
fi
