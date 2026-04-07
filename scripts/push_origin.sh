#!/usr/bin/env bash
set -euo pipefail

WORKSPACE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$WORKSPACE_ROOT"

ALLOW_DIRTY=0
TARGET_BRANCH=""

show_help() {
  cat <<'EOF'
Usage: bash scripts/push_origin.sh [OPTIONS]

Push the current branch to origin as the canonical remote reflection step.

Options:
  --branch <name>   Push the specified local branch instead of the current branch
  --allow-dirty     Allow push even when the worktree is not clean
  -h, --help        Show this help
EOF
}

require_value() {
  local option_name="$1"
  if [[ $# -lt 2 || -z "${2:-}" ]]; then
    echo "Missing value for ${option_name}" >&2
    exit 1
  fi
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --branch)
      require_value "$1" "${2:-}"
      TARGET_BRANCH="$2"
      shift 2
      ;;
    --allow-dirty)
      ALLOW_DIRTY=1
      shift
      ;;
    -h|--help)
      show_help
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      show_help >&2
      exit 1
      ;;
  esac
done

if [[ -z "$TARGET_BRANCH" ]]; then
  TARGET_BRANCH="$(git symbolic-ref --quiet --short HEAD)" || {
    echo "Detached HEAD is not allowed. Check out a branch before pushing." >&2
    exit 1
  }
fi

if [[ "$ALLOW_DIRTY" -eq 0 ]] && [[ -n "$(git status --short --untracked-files=all)" ]]; then
  echo "Worktree is not clean. Commit, stash, or pass --allow-dirty before pushing." >&2
  exit 1
fi

if [[ "$TARGET_BRANCH" == "main" ]]; then
  echo "Pushing main to origin..."
  git push origin main
else
  echo "Pushing branch '${TARGET_BRANCH}' to origin..."
  git push -u origin "$TARGET_BRANCH"
fi

echo ""
echo "Origin push completed."
