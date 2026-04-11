#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(git -C "$(dirname "${BASH_SOURCE[0]}")" rev-parse --show-toplevel)"
PREFIX="${AGENT_CANON_PREFIX:-vendor/agent-canon}"
REMOTE_NAME="${AGENT_CANON_REMOTE_NAME:-agent-canon}"
DEFAULT_BRANCH="${AGENT_CANON_BRANCH:-main}"

usage() {
  cat <<EOF
Usage:
  bash tools/update_agent_canon.sh plan [branch]
  bash tools/update_agent_canon.sh apply [branch]
  bash tools/update_agent_canon.sh register-remote <remote-url>
  bash tools/update_agent_canon.sh register-local-bare --bare-repo <path>.git [--branch <branch>]

Commands:
  plan
      Print the derived-repo update route for agent-canon only.
  apply
      Update vendor/agent-canon only by delegating to sync_agent_canon.sh ensure-latest.
  register-remote
      Configure or replace the '${REMOTE_NAME}' remote.
  register-local-bare
      Initialize or reuse a project-local bare repo, seed it from the current
      vendor/agent-canon snapshot when needed, and point '${REMOTE_NAME}' at it.
EOF
}

die() {
  echo "update_agent_canon.sh: $*" >&2
  exit 1
}

cmd_plan() {
  local branch="${1:-$DEFAULT_BRANCH}"
  bash "$ROOT_DIR/tools/sync_agent_canon.sh" plan "$branch"
}

cmd_apply() {
  local branch="${1:-$DEFAULT_BRANCH}"
  bash "$ROOT_DIR/tools/sync_agent_canon.sh" ensure-latest "$branch"
}

cmd_register_remote() {
  local remote_url="${1:-}"
  [ -n "$remote_url" ] || die "register-remote requires <remote-url>"
  if git -C "$ROOT_DIR" remote get-url "$REMOTE_NAME" >/dev/null 2>&1; then
    git -C "$ROOT_DIR" remote set-url "$REMOTE_NAME" "$remote_url"
    echo "agent_canon_remote_updated=$remote_url"
  else
    git -C "$ROOT_DIR" remote add "$REMOTE_NAME" "$remote_url"
    echo "agent_canon_remote_added=$remote_url"
  fi
}

seed_snapshot_into_bare() {
  local bare_repo_path="$1"
  local branch="$2"
  local seed_sha=""

  if git --git-dir="$bare_repo_path" rev-parse --verify "refs/heads/$branch" >/dev/null 2>&1; then
    echo "agent_canon_bare_repo=already_has_${branch}:${bare_repo_path}"
    return
  fi

  if git subtree --help >/dev/null 2>&1; then
    seed_sha="$(git -C "$ROOT_DIR" subtree split --prefix="$PREFIX" HEAD)"
    echo "agent_canon_seed_method=subtree_split"
  else
    seed_sha="$(git -C "$ROOT_DIR" commit-tree "HEAD:$PREFIX" -m "chore: seed agent-canon snapshot")"
    echo "agent_canon_seed_method=commit_tree_snapshot"
  fi

  git -C "$ROOT_DIR" push "$bare_repo_path" "${seed_sha}:refs/heads/${branch}" >/dev/null
  git --git-dir="$bare_repo_path" symbolic-ref HEAD "refs/heads/${branch}"
  echo "seeded agent_canon_bare_repo=${bare_repo_path}"
}

cmd_register_local_bare() {
  local bare_repo_path=""
  local branch="$DEFAULT_BRANCH"

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --bare-repo)
        bare_repo_path="${2:-}"
        shift 2
        ;;
      --branch)
        branch="${2:-}"
        shift 2
        ;;
      -h|--help)
        usage
        exit 0
        ;;
      *)
        die "unknown register-local-bare option '$1'"
        ;;
    esac
  done

  [ -n "$bare_repo_path" ] || die "register-local-bare requires --bare-repo <path>.git"
  [ -d "$ROOT_DIR/$PREFIX" ] || die "prefix '$PREFIX' does not exist"

  mkdir -p "$(dirname "$bare_repo_path")"
  if [[ ! -d "$bare_repo_path" ]]; then
    git init --bare "$bare_repo_path" >/dev/null
    echo "created agent_canon_bare_repo=$bare_repo_path"
  fi

  seed_snapshot_into_bare "$bare_repo_path" "$branch"
  cmd_register_remote "$bare_repo_path"
  echo "agent_canon_register_next=bash tools/update_agent_canon.sh plan $branch"
}

main() {
  local subcommand="${1:-}"
  case "$subcommand" in
    plan)
      shift
      cmd_plan "${1:-$DEFAULT_BRANCH}"
      ;;
    apply)
      shift
      cmd_apply "${1:-$DEFAULT_BRANCH}"
      ;;
    register-remote)
      shift
      cmd_register_remote "${1:-}"
      ;;
    register-local-bare)
      shift
      cmd_register_local_bare "$@"
      ;;
    -h|--help|help|"")
      usage
      ;;
    *)
      die "unknown subcommand '$subcommand'"
      ;;
  esac
}

main "$@"
