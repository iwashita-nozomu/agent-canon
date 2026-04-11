#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(git -C "$(dirname "${BASH_SOURCE[0]}")" rev-parse --show-toplevel)"
PREFIX="${AGENT_CANON_PREFIX:-vendor/agent-canon}"
REMOTE_NAME="${AGENT_CANON_REMOTE_NAME:-agent-canon}"
DEFAULT_BRANCH="${AGENT_CANON_BRANCH:-main}"
DEFAULT_PROPOSAL_PREFIX="${AGENT_CANON_PROPOSAL_PREFIX:-canon-proposal}"

usage() {
  cat <<EOF
Usage:
  bash tools/update_agent_canon.sh plan [branch]
  bash tools/update_agent_canon.sh apply [branch]
  bash tools/update_agent_canon.sh register-remote <remote-url>
  bash tools/update_agent_canon.sh proposal-branch [--proposal-branch <name>]
  bash tools/update_agent_canon.sh push-proposal [proposal-branch]
  bash tools/update_agent_canon.sh register-local-bare --bare-repo <path>.git [--branch <branch>] [--proposal-branch <name>]

Commands:
  plan
      Print the derived-repo update route for agent-canon only.
  apply
      Update vendor/agent-canon only by delegating to sync_agent_canon.sh ensure-latest.
  register-remote
      Configure or replace the '${REMOTE_NAME}' remote.
  proposal-branch
      Print the configured or derived branch that should receive shared-canon
      proposals from this derived repository.
  push-proposal
      Push the current vendor/agent-canon snapshot to the proposal branch.
  register-local-bare
      Initialize or reuse a project-local bare repo, seed it from the current
      vendor/agent-canon snapshot when needed, prepare the proposal branch, and
      point '${REMOTE_NAME}' at it.
EOF
}

die() {
  echo "update_agent_canon.sh: $*" >&2
  exit 1
}

sanitize_branch_slug() {
  local raw="${1:-}"
  raw="$(printf '%s' "$raw" | tr '[:upper:]' '[:lower:]')"
  raw="$(printf '%s' "$raw" | sed -E 's/[^a-z0-9._-]+/-/g; s#^[./-]+##; s#[./-]+$##; s/-+/-/g')"
  if [[ -z "$raw" ]]; then
    raw="derived-repo"
  fi
  printf '%s\n' "$raw"
}

default_proposal_branch_name() {
  local bare_repo_path="${1:-}"
  local bare_name=""
  local slug=""

  if [[ -n "${AGENT_CANON_PROPOSAL_BRANCH:-}" ]]; then
    printf '%s\n' "${AGENT_CANON_PROPOSAL_BRANCH}"
    return
  fi

  if git -C "$ROOT_DIR" config --get "${REMOTE_NAME}.proposalBranch" >/dev/null 2>&1; then
    git -C "$ROOT_DIR" config --get "${REMOTE_NAME}.proposalBranch"
    return
  fi

  if [[ -n "$bare_repo_path" ]]; then
    bare_name="$(basename "$bare_repo_path")"
    bare_name="${bare_name%.git}"
    bare_name="${bare_name%-agent-canon}"
    slug="$(sanitize_branch_slug "$bare_name")"
  else
    slug="$(sanitize_branch_slug "$(basename "$ROOT_DIR")")"
  fi

  printf '%s/%s\n' "$DEFAULT_PROPOSAL_PREFIX" "$slug"
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

cmd_proposal_branch() {
  local explicit_branch=""

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --proposal-branch)
        explicit_branch="${2:-}"
        shift 2
        ;;
      -h|--help)
        usage
        exit 0
        ;;
      *)
        die "unknown proposal-branch option '$1'"
        ;;
    esac
  done

  if [[ -n "$explicit_branch" ]]; then
    echo "agent_canon_proposal_branch=$explicit_branch"
    echo "agent_canon_proposal_branch_source=explicit"
    return
  fi

  if [[ -n "${AGENT_CANON_PROPOSAL_BRANCH:-}" ]]; then
    echo "agent_canon_proposal_branch=${AGENT_CANON_PROPOSAL_BRANCH}"
    echo "agent_canon_proposal_branch_source=environment"
    return
  fi

  if git -C "$ROOT_DIR" config --get "${REMOTE_NAME}.proposalBranch" >/dev/null 2>&1; then
    echo "agent_canon_proposal_branch=$(git -C "$ROOT_DIR" config --get "${REMOTE_NAME}.proposalBranch")"
    echo "agent_canon_proposal_branch_source=git_config"
    return
  fi

  echo "agent_canon_proposal_branch=$(default_proposal_branch_name)"
  echo "agent_canon_proposal_branch_source=derived"
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

ensure_bare_branch_exists() {
  local bare_repo_path="$1"
  local base_branch="$2"
  local proposal_branch="$3"
  local base_ref="refs/heads/$base_branch"
  local proposal_ref="refs/heads/$proposal_branch"

  git --git-dir="$bare_repo_path" rev-parse --verify "$base_ref" >/dev/null 2>&1 || \
    die "base branch '$base_branch' does not exist in bare repo '$bare_repo_path'"

  if git --git-dir="$bare_repo_path" rev-parse --verify "$proposal_ref" >/dev/null 2>&1; then
    echo "agent_canon_proposal_branch=already_has_${proposal_branch}:${bare_repo_path}"
    return
  fi

  git --git-dir="$bare_repo_path" update-ref "$proposal_ref" "$base_ref"
  echo "created agent_canon_proposal_branch=${proposal_branch}"
}

cmd_register_local_bare() {
  local bare_repo_path=""
  local branch="$DEFAULT_BRANCH"
  local proposal_branch=""

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
      --proposal-branch)
        proposal_branch="${2:-}"
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
  if [[ -z "$proposal_branch" ]]; then
    proposal_branch="$(default_proposal_branch_name "$bare_repo_path")"
  fi
  ensure_bare_branch_exists "$bare_repo_path" "$branch" "$proposal_branch"
  cmd_register_remote "$bare_repo_path"
  git -C "$ROOT_DIR" config "${REMOTE_NAME}.proposalBranch" "$proposal_branch"
  echo "agent_canon_proposal_branch=$proposal_branch"
  echo "agent_canon_register_next=bash tools/update_agent_canon.sh plan $branch"
  echo "agent_canon_proposal_next=bash tools/update_agent_canon.sh push-proposal"
}

cmd_push_proposal() {
  local proposal_branch="${1:-}"
  if [[ -z "$proposal_branch" ]]; then
    proposal_branch="$(default_proposal_branch_name)"
  fi

  echo "agent_canon_push_target=$proposal_branch"
  bash "$ROOT_DIR/tools/sync_agent_canon.sh" push "$proposal_branch"
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
    proposal-branch)
      shift
      cmd_proposal_branch "$@"
      ;;
    push-proposal)
      shift
      cmd_push_proposal "${1:-}"
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
