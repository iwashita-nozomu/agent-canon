#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(git -C "$(dirname "${BASH_SOURCE[0]}")" rev-parse --show-toplevel)"
PREFIX="${AGENT_CANON_PREFIX:-vendor/agent-canon}"
REMOTE_NAME="${AGENT_CANON_REMOTE_NAME:-agent-canon}"
DEFAULT_BRANCH="${AGENT_CANON_BRANCH:-main}"
DEFAULT_PROPOSAL_PREFIX="${AGENT_CANON_PROPOSAL_PREFIX:-canon-proposal}"
DEFAULT_SHARED_SOURCE_REPO="${AGENT_CANON_SOURCE_REPO:-/mnt/l/workspace/agent-canon}"

usage() {
  cat <<EOF
Usage:
  bash tools/update_agent_canon.sh plan [branch]
  bash tools/update_agent_canon.sh apply [branch]
  bash tools/update_agent_canon.sh refresh-remote [branch]
  bash tools/update_agent_canon.sh register-remote <remote-url>
  bash tools/update_agent_canon.sh proposal-branch [--proposal-branch <name>]
  bash tools/update_agent_canon.sh push-proposal [proposal-branch]
  bash tools/update_agent_canon.sh register-local-bare --bare-repo <path>.git [--branch <branch>] [--proposal-branch <name>] [--source-repo <path>]

Commands:
  plan
      Print the derived-repo update route for agent-canon only.
  apply
      Refresh the remote snapshot from the source repo when configured, then update
      vendor/agent-canon via sync_agent_canon.sh ensure-latest.
  refresh-remote
      Push the configured source repo branch to the agent-canon remote before a local import.
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

configured_source_repo() {
  if [[ -n "${AGENT_CANON_SOURCE_REPO:-}" ]]; then
    printf '%s\n' "${AGENT_CANON_SOURCE_REPO}"
    return
  fi
  if git -C "$ROOT_DIR" config --get "${REMOTE_NAME}.sourceRepo" >/dev/null 2>&1; then
    git -C "$ROOT_DIR" config --get "${REMOTE_NAME}.sourceRepo"
    return
  fi
}

configured_remote_url() {
  if git -C "$ROOT_DIR" remote get-url "$REMOTE_NAME" >/dev/null 2>&1; then
    git -C "$ROOT_DIR" remote get-url "$REMOTE_NAME"
    return
  fi
  default_remote_url || true
}

cmd_refresh_remote() {
  local branch="${1:-$DEFAULT_BRANCH}"
  local remote_url=""
  local source_repo=""
  local source_sha=""
  local remote_sha=""

  remote_url="$(configured_remote_url)"
  [ -n "$remote_url" ] || die "remote '$REMOTE_NAME' is not configured"

  source_repo="$(configured_source_repo || true)"
  [ -n "$source_repo" ] || die "source repo for '$REMOTE_NAME' is not configured"
  [ -d "$source_repo/.git" ] || die "source repo does not exist: $source_repo"

  if [[ -n "$(git -C "$source_repo" status --short)" ]]; then
    die "source repo is dirty: $source_repo"
  fi

  source_sha="$(git -C "$source_repo" rev-parse "refs/heads/${branch}")"
  remote_sha="$(git ls-remote "$remote_url" "refs/heads/${branch}" | awk '{print $1}')"

  echo "agent_canon_refresh_source_repo=$source_repo"
  echo "agent_canon_refresh_remote_url=$remote_url"
  echo "agent_canon_refresh_branch=$branch"
  echo "agent_canon_refresh_source_sha=$source_sha"
  if [[ -n "$remote_sha" ]]; then
    echo "agent_canon_refresh_remote_sha=$remote_sha"
  else
    echo "agent_canon_refresh_remote_sha=<unset>"
  fi

  if [[ "$remote_sha" = "$source_sha" ]]; then
    echo "agent_canon_refresh_status=already_current"
    return
  fi

  git -C "$source_repo" push "$remote_url" "refs/heads/${branch}:refs/heads/${branch}" >/dev/null
  echo "agent_canon_refresh_status=updated_remote_snapshot"
}

cmd_plan() {
  local branch="${1:-$DEFAULT_BRANCH}"
  local source_repo=""
  local remote_url=""
  local source_sha=""
  local remote_sha=""
  source_repo="$(configured_source_repo || true)"
  if [[ -n "$source_repo" ]]; then
    echo "agent_canon_plan_source_repo=$source_repo"
    echo "agent_canon_plan_apply_order=refresh_remote_snapshot_then_local_sync"
    [ -d "$source_repo/.git" ] || die "configured source repo does not exist: $source_repo"
    if [[ -n "$(git -C "$source_repo" status --short)" ]]; then
      die "source repo is dirty: $source_repo"
    fi
    remote_url="$(configured_remote_url)"
    [ -n "$remote_url" ] || die "remote '$REMOTE_NAME' is not configured"
    source_sha="$(git -C "$source_repo" rev-parse "refs/heads/${branch}")"
    remote_sha="$(git ls-remote "$remote_url" "refs/heads/${branch}" | awk '{print $1}')"
    echo "agent_canon_plan_refresh_remote_url=$remote_url"
    echo "agent_canon_plan_effective_remote_url=$source_repo"
    echo "agent_canon_plan_source_sha=$source_sha"
    if [[ -n "$remote_sha" ]]; then
      echo "agent_canon_plan_refresh_remote_sha=$remote_sha"
    else
      echo "agent_canon_plan_refresh_remote_sha=<unset>"
    fi
    if [[ "$remote_sha" = "$source_sha" ]]; then
      echo "agent_canon_plan_refresh_status=already_current"
    else
      echo "agent_canon_plan_refresh_status=will_update_remote_snapshot"
    fi
    AGENT_CANON_PLAN_REMOTE_URL="$source_repo" \
      bash "$ROOT_DIR/tools/sync_agent_canon.sh" plan "$branch"
    return
  else
    echo "agent_canon_plan_source_repo=<unset>"
    echo "agent_canon_plan_apply_order=local_sync_only"
  fi
  bash "$ROOT_DIR/tools/sync_agent_canon.sh" plan "$branch"
}

cmd_apply() {
  local branch="${1:-$DEFAULT_BRANCH}"
  if [[ -n "$(configured_source_repo || true)" ]]; then
    cmd_refresh_remote "$branch"
  fi
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
  local source_repo=""

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
      --source-repo)
        source_repo="${2:-}"
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
  if [[ -n "$source_repo" ]]; then
    git -C "$ROOT_DIR" config "${REMOTE_NAME}.sourceRepo" "$source_repo"
    echo "agent_canon_source_repo=$source_repo"
  else
    git -C "$ROOT_DIR" config --unset-all "${REMOTE_NAME}.sourceRepo" >/dev/null 2>&1 || true
    echo "agent_canon_source_repo=<unset>"
  fi
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
    refresh-remote)
      shift
      cmd_refresh_remote "${1:-$DEFAULT_BRANCH}"
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
