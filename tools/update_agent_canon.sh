#!/usr/bin/env bash
# @dependency-start
# responsibility Provides GitHub-first AgentCanon submodule update automation.
# upstream design ../documents/github-first-module-and-devcontainer-policy.md defines GitHub-first module policy.
# upstream design ../documents/agent-canon-github-remote.md defines the canonical AgentCanon GitHub remote.
# upstream implementation ./sync_agent_canon.sh performs low-level submodule freshness and root-view synchronization.
# downstream implementation ../tests/tools/test_update_agent_canon.py validates update wrapper behavior.
# @dependency-end

set -euo pipefail
export GIT_TERMINAL_PROMPT="${GIT_TERMINAL_PROMPT:-0}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
SUPERPROJECT_DIR="$(git -C "$SCRIPT_DIR" rev-parse --show-superproject-working-tree 2>/dev/null || true)"
if [ -n "$SUPERPROJECT_DIR" ]; then
  ROOT_DIR="$SUPERPROJECT_DIR"
else
  ROOT_DIR="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel)"
fi
PREFIX="${AGENT_CANON_PREFIX:-vendor/agent-canon}"
DEFAULT_BRANCH="${AGENT_CANON_BRANCH:-main}"

usage() {
  cat <<EOF
Usage:
  bash tools/update_agent_canon.sh plan [branch]
  bash tools/update_agent_canon.sh apply [branch]
  bash tools/update_agent_canon.sh merge-main-into-current [branch]
  bash tools/update_agent_canon.sh status

Commands:
  plan
      Print the AgentCanon update route for the current parent repo.
  apply
      Update the parent repo to AgentCanon main when the update surface is safe.
  merge-main-into-current
      Inside vendor/agent-canon, fetch AgentCanon main and merge it into the
      currently checked-out AgentCanon branch. This is the canonical repair path
      for local AgentCanon branches that need to be brought near GitHub main
      before pushing an AgentCanon PR branch.
  status
      Print low-level AgentCanon submodule/root-view status.

Removed user-facing commands:
  Compatibility commands for local remotes, local source refresh, and direct
  main alignment were removed from this wrapper. GitHub-backed repos should
  push a normal AgentCanon branch and PR instead.
EOF
}

die() {
  echo "update_agent_canon.sh: $*" >&2
  exit 1
}

ensure_agent_canon_submodule() {
  [ -d "$ROOT_DIR/$PREFIX" ] || die "prefix '$PREFIX' does not exist"
  [ "$(git -C "$ROOT_DIR" ls-tree HEAD "$PREFIX" 2>/dev/null | awk '{print $1}')" = "160000" ] \
    || die "prefix '$PREFIX' is not a Git submodule"
  if ! git -C "$ROOT_DIR/$PREFIX" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    git -C "$ROOT_DIR" submodule update --init --recursive "$PREFIX" >/dev/null
  fi
}

submodule_remote_url() {
  git -C "$ROOT_DIR" config -f .gitmodules --get "submodule.${PREFIX}.url" 2>/dev/null || true
}

sanitize_ref_component() {
  local raw="${1:-}"
  raw="$(printf '%s' "$raw" | tr '[:upper:]' '[:lower:]')"
  raw="$(printf '%s' "$raw" | sed -E 's#[^a-z0-9._/-]+#-#g; s#^[./-]+##; s#[./-]+$##; s#/{2,}#/#g; s#-+#-#g')"
  if [[ -z "$raw" ]]; then
    raw="detached"
  fi
  printf '%s\n' "$raw"
}

parent_pin() {
  git -C "$ROOT_DIR" rev-parse "HEAD:$PREFIX"
}

parent_pin_pending() {
  local post_head="$1"
  if [ "$(parent_pin)" = "$post_head" ]; then
    echo "no"
  else
    echo "yes"
  fi
}

cmd_plan() {
  local branch="${1:-$DEFAULT_BRANCH}"
  bash "$ROOT_DIR/tools/sync_agent_canon.sh" plan "$branch"
}

cmd_apply() {
  local branch="${1:-$DEFAULT_BRANCH}"
  bash "$ROOT_DIR/tools/sync_agent_canon.sh" ensure-latest "$branch"
}

cmd_status() {
  bash "$ROOT_DIR/tools/sync_agent_canon.sh" status
}

cmd_merge_main_into_current() {
  local branch="${1:-$DEFAULT_BRANCH}"
  local remote_url=""
  local remote_sha=""
  local pre_head=""
  local post_head=""
  local current_branch=""
  local submodule_status=""
  local backup_branch=""
  local backup_ref=""
  local timestamp=""
  local merge_log=""
  local result=""
  local conflict_files=""

  ensure_agent_canon_submodule
  remote_url="$(submodule_remote_url)"
  [ -n "$remote_url" ] || die "submodule '$PREFIX' has no .gitmodules url"

  git -C "$ROOT_DIR/$PREFIX" fetch "$remote_url" "$branch" >/dev/null
  remote_sha="$(git -C "$ROOT_DIR/$PREFIX" rev-parse FETCH_HEAD)"
  pre_head="$(git -C "$ROOT_DIR/$PREFIX" rev-parse HEAD)"
  current_branch="$(git -C "$ROOT_DIR/$PREFIX" symbolic-ref --quiet --short HEAD 2>/dev/null || true)"
  submodule_status="$(git -C "$ROOT_DIR/$PREFIX" status --short --untracked-files=all)"

  echo "agent_canon_merge_prefix=$PREFIX"
  echo "agent_canon_merge_source=${remote_url}#${branch}"
  echo "agent_canon_merge_source_sha=$remote_sha"
  echo "agent_canon_merge_target_branch=${current_branch:-<detached>}"
  echo "agent_canon_merge_pre_head=$pre_head"

  if [ -n "$submodule_status" ]; then
    echo "agent_canon_merge_worktree_status=dirty"
    echo "agent_canon_merge_result=blocked_dirty"
    echo "agent_canon_parent_pin_pending=$(parent_pin_pending "$pre_head")"
    echo "NEXT_ACTION=commit_or_stash_agentcanon_changes_then_rerun_merge-main-into-current"
    die "submodule '$PREFIX' has uncommitted changes; commit or stash them before merging main"
  fi
  echo "agent_canon_merge_worktree_status=clean"

  if [ -z "$current_branch" ]; then
    echo "agent_canon_merge_result=blocked_detached_head"
    echo "agent_canon_parent_pin_pending=$(parent_pin_pending "$pre_head")"
    echo "NEXT_ACTION=create_agentcanon_branch_then_rerun_merge-main-into-current"
    die "submodule '$PREFIX' is detached; create or switch to a branch before merging main"
  fi

  if [ "$pre_head" = "$remote_sha" ]; then
    echo "agent_canon_merge_post_head=$pre_head"
    echo "agent_canon_merge_result=already_current"
    echo "agent_canon_parent_pin_pending=$(parent_pin_pending "$pre_head")"
    echo "NEXT_ACTION=continue_parent_workflow"
    return
  fi

  timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
  backup_branch="agent-canon-merge-backup/$(sanitize_ref_component "$current_branch")/$timestamp"
  backup_ref="refs/heads/$backup_branch"
  git -C "$ROOT_DIR/$PREFIX" branch "$backup_branch" "$pre_head" >/dev/null
  echo "agent_canon_merge_backup_ref=$backup_ref"

  if git -C "$ROOT_DIR/$PREFIX" merge-base --is-ancestor "$remote_sha" "$pre_head"; then
    echo "agent_canon_merge_post_head=$pre_head"
    echo "agent_canon_merge_result=already_contains_main"
    echo "agent_canon_parent_pin_pending=$(parent_pin_pending "$pre_head")"
    echo "NEXT_ACTION=push_current_agentcanon_branch_and_open_or_update_PR"
    return
  fi

  merge_log="$(mktemp)"
  if git -C "$ROOT_DIR/$PREFIX" merge --no-edit FETCH_HEAD >"$merge_log" 2>&1; then
    post_head="$(git -C "$ROOT_DIR/$PREFIX" rev-parse HEAD)"
    if git -C "$ROOT_DIR/$PREFIX" merge-base --is-ancestor "$pre_head" "$remote_sha"; then
      result="fast_forwarded"
    else
      result="merged"
    fi
    rm -f "$merge_log"
    echo "agent_canon_merge_post_head=$post_head"
    echo "agent_canon_merge_result=$result"
    echo "agent_canon_parent_pin_pending=$(parent_pin_pending "$post_head")"
    echo "NEXT_ACTION=run_validation_then_push_current_agentcanon_branch_and_open_or_update_PR"
    return
  fi

  cat "$merge_log" >&2
  rm -f "$merge_log"
  conflict_files="$(git -C "$ROOT_DIR/$PREFIX" diff --name-only --diff-filter=U | paste -sd, -)"
  echo "agent_canon_merge_result=conflict"
  echo "agent_canon_merge_conflict_files=${conflict_files:-<unset>}"
  echo "agent_canon_parent_pin_pending=$(parent_pin_pending "$pre_head")"
  echo "NEXT_ACTION=resolve_agentcanon_merge_conflicts_then_commit_and_push_current_branch"
  exit 1
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
    merge-main-into-current)
      shift
      cmd_merge_main_into_current "${1:-$DEFAULT_BRANCH}"
      ;;
    status)
      shift
      cmd_status
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
