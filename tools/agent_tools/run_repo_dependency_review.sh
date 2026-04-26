#!/usr/bin/env bash
# @dependency-start
# upstream design ../../documents/dependency-manifest-design.md dependency review policy
# upstream implementation ./scan_dependency_headers.sh scans repo-wide manifest coverage
# upstream implementation ./check_dependency_header_format.sh validates repo-wide manifest syntax
# upstream implementation ./check_dependency_graph.sh validates repo-wide dependency graph
# downstream implementation ../../tests/agent_tools/test_dependency_manifest_tools.py verifies wrapper behavior
# @dependency-end
set -euo pipefail

ROOT_DIR="$(git -C "$(dirname "${BASH_SOURCE[0]}")" rev-parse --show-toplevel 2>/dev/null || pwd)"
CHECK_BIDIRECTIONAL=0

usage() {
  cat <<'EOF'
Usage:
  run_repo_dependency_review.sh [--root DIR] [--check-bidirectional]

Runs dependency manifest review against all tracked, checkable text files in the repo.
This is intended for checkpoint and final review, not just changed-file closeout.
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

bash tools/agent_tools/scan_dependency_headers.sh --fail-missing "${checkable_paths[@]}"
bash tools/agent_tools/check_dependency_header_format.sh --require-header "${checkable_paths[@]}"

graph_args=(tools/agent_tools/check_dependency_graph.sh)
if [[ "$CHECK_BIDIRECTIONAL" -eq 1 ]]; then
  graph_args+=(--check-bidirectional)
fi
bash "${graph_args[@]}" "${checkable_paths[@]}"

echo "REPO_DEPENDENCY_REVIEW=pass"
