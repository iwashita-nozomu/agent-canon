#!/usr/bin/env bash
# @dependency-start
# responsibility Runs repo dependency review agent workflow automation.
# upstream design ../../documents/dependency-manifest-design.md dependency review policy
# upstream design ../../agents/canonical/CODEX_WORKFLOW.md closeout requires dependency evidence
# upstream design ../../agents/templates/closeout_gate.md closeout dependency evidence gate
# upstream design ../../.github/PULL_REQUEST_TEMPLATE.md standalone PR dependency checklist
# upstream design ../../.github/PULL_REQUEST_TEMPLATE/agent_canon.md template PR dependency checklist
# upstream implementation ./scan_dependency_headers.sh scans repo-wide manifest coverage
# upstream implementation ./check_dependency_header_format.sh validates repo-wide manifest syntax
# upstream implementation ./check_dependency_graph.sh validates repo-wide dependency graph
# downstream implementation ../../tools/ci/check_agent_canon_pr.sh runs strict dependency review
# downstream implementation ../../tests/agent_tools/test_dependency_manifest_tools.py verifies wrapper behavior
# @dependency-end
set -euo pipefail

ROOT_DIR="$(git -C "$PWD" rev-parse --show-toplevel 2>/dev/null || pwd)"
CHECK_BIDIRECTIONAL=0
FAIL_MISSING=0
ALLOW_FRONTMATTER=0
EXPLAIN_MISSING=0
REPORT_DIR="${AGENT_RUN_REPORT_DIR:-}"

usage() {
  cat <<'EOF'
Usage:
  run_repo_dependency_review.sh [--root DIR] [--check-bidirectional] [--fail-missing] [--allow-frontmatter] [--explain-missing] [--report-dir DIR]

Runs dependency manifest review against all tracked, checkable text files in the repo.
This is intended for checkpoint and final review, not just changed-file closeout.
Missing manifests are report-only by default until the repository-wide migration is complete.
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
    --report-dir)
      REPORT_DIR="$2"
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

cd "$ROOT_DIR"

mapfile -t checkable_paths < <(
  git ls-files | awk '
    /^reports\/agents\// { next }
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

graph_args=(tools/agent_tools/check_dependency_graph.sh)
if [[ "$CHECK_BIDIRECTIONAL" -eq 1 ]]; then
  graph_args+=(--check-bidirectional)
fi
if [[ "$ALLOW_FRONTMATTER" -eq 1 ]]; then
  graph_args+=(--allow-frontmatter)
fi
bash "${graph_args[@]}" "${checkable_paths[@]}"

echo "REPO_DEPENDENCY_REVIEW=pass"

if [[ -n "$REPORT_DIR" ]]; then
  python3 tools/agent_tools/workflow_monitor.py \
    --report-dir "$REPORT_DIR" \
    --signal "repo_dependency_review=pass paths=${#checkable_paths[@]} check_bidirectional=${CHECK_BIDIRECTIONAL} fail_missing=${FAIL_MISSING}" \
    --intervention "run_repo_dependency_review.sh recorded dependency review pass"
fi
