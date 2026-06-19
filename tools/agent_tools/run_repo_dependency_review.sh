#!/usr/bin/env bash
# @dependency-start
# contract tool
# responsibility Runs repo dependency review agent workflow automation.
# upstream design ../../documents/dependency-manifest-design.md dependency review policy
# upstream design ../../agents/canonical/CODEX_WORKFLOW.md closeout requires dependency evidence
# upstream design ../../agents/templates/closeout_gate.md closeout dependency evidence gate
# upstream design ../../.github/PULL_REQUEST_TEMPLATE.md standalone PR dependency checklist
# upstream design ../../.github/PULL_REQUEST_TEMPLATE/agent_canon.md template PR dependency checklist
# upstream implementation ./scan_dependency_headers.sh scans repo-wide manifest coverage
# upstream implementation ./check_dependency_header_format.sh validates repo-wide manifest syntax
# upstream implementation ./check_dependency_graph.sh validates repo-wide dependency graph
# upstream implementation ./check_design_doc_claims.py validates design claims against dependency evidence
# downstream implementation ../../tools/ci/check_agent_canon_pr.sh runs strict dependency review
# downstream implementation ../../tests/agent_tools/test_dependency_manifest_tools.py verifies wrapper behavior
# @dependency-end
set -euo pipefail

ROOT_DIR="$(git -C "$PWD" rev-parse --show-toplevel 2>/dev/null || pwd)"
CHECK_BIDIRECTIONAL=0
CYCLE_REPORT_ONLY=0
FAIL_MISSING=0
ALLOW_FRONTMATTER=0
EXPLAIN_MISSING=0
LIST_CHANGED_DEPENDENCIES=0
REPORT_DIR="${AGENT_RUN_REPORT_DIR:-}"
GRAPH_TSV_OUTPUT=""
SEARCH_HITS_FILE=""
CHECK_DESIGN_DOC_CLAIMS=0
declare -a DESIGN_DOC_CLAIM_PATHS=()

usage() {
  cat <<'EOF'
Usage:
  run_repo_dependency_review.sh [--root DIR] [--check-bidirectional] [--cycle-report-only] [--fail-missing] [--allow-frontmatter] [--explain-missing] [--list-changed-dependencies] [--report-dir DIR] [--graph-tsv PATH] [--search-hits-file PATH] [--check-design-doc-claims] [--design-doc-claim-path PATH]

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

ROOT_DIR="$(realpath -m "$ROOT_DIR")"
cd "$ROOT_DIR"

mapfile -t checkable_paths < <(
  git ls-files | awk '
    /^reports\/agents\// { next }
    /^reports\/dependency-review\// { next }
    /\.(bash|cfg|css|h|hpp|html|c|cc|cpp|json|md|py|rst|sh|toml|txt|yaml|yml|zsh)$/ { print }
  '
)

echo "REPO_DEPENDENCY_REVIEW_PATHS=${#checkable_paths[@]}"

scan_args=(tools/agent_tools/scan_dependency_headers.sh)
format_args=(tools/agent_tools/check_dependency_header_format.sh)
if [[ "$FAIL_MISSING" -eq 1 ]]; then
  scan_args+=(--fail-missing)
  format_args+=(--require-header)
fi
if [[ "$ALLOW_FRONTMATTER" -eq 1 ]]; then
  scan_args+=(--allow-frontmatter)
  format_args+=(--allow-frontmatter)
fi
if [[ "$EXPLAIN_MISSING" -eq 1 ]]; then
  scan_args+=(--explain-missing)
fi

bash "${scan_args[@]}" "${checkable_paths[@]}"
bash "${format_args[@]}" "${checkable_paths[@]}"

if [[ -n "$REPORT_DIR" ]]; then
  mkdir -p "$REPORT_DIR"
fi
if [[ -z "$GRAPH_TSV_OUTPUT" && -n "$REPORT_DIR" ]]; then
  GRAPH_TSV_OUTPUT="$REPORT_DIR/dependency_graph.tsv"
fi

graph_args=(tools/agent_tools/check_dependency_graph.sh)
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
  related_args=(tools/agent_tools/check_dependency_graph.sh --list-related --focus-changed)
  if [[ "$CYCLE_REPORT_ONLY" -eq 1 ]]; then
    related_args+=(--cycle-report-only)
  fi
  if [[ "$ALLOW_FRONTMATTER" -eq 1 ]]; then
    related_args+=(--allow-frontmatter)
  fi
  bash "${related_args[@]}" "${checkable_paths[@]}"
fi

if [[ "$CHECK_DESIGN_DOC_CLAIMS" -eq 1 ]]; then
  design_claim_args=(tools/agent_tools/check_design_doc_claims.py --root "$ROOT_DIR")
  if [[ ${#DESIGN_DOC_CLAIM_PATHS[@]} -gt 0 ]]; then
    design_claim_args+=("${DESIGN_DOC_CLAIM_PATHS[@]}")
  else
    design_claim_args+=(--changed)
  fi
  python3 "${design_claim_args[@]}"
fi

if [[ -n "$SEARCH_HITS_FILE" ]]; then
  edit_scope_args=(tools/agent_tools/check_dependency_graph.sh --search-hits-file "$SEARCH_HITS_FILE")
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
  edit_scope_args=(tools/agent_tools/check_dependency_graph.sh --edit-scope-changed)
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
  python3 tools/agent_tools/workflow_monitor.py \
    --report-dir "$REPORT_DIR" \
    --signal "repo_dependency_review=pass paths=${#checkable_paths[@]} check_bidirectional=${CHECK_BIDIRECTIONAL} fail_missing=${FAIL_MISSING}" \
    --intervention "run_repo_dependency_review.sh recorded dependency review pass"
fi
