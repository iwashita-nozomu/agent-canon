#!/usr/bin/env bash
# @dependency-start
# responsibility Provides GitHub-first AgentCanon submodule update automation.
# upstream design ../documents/github-first-module-and-devcontainer-policy.md defines GitHub-first module policy.
# upstream design ../documents/agent-canon-github-remote.md defines the canonical AgentCanon GitHub remote.
# upstream implementation ./sync_agent_canon.sh performs low-level submodule freshness and root-view synchronization.
# upstream implementation ./rebuild_agent_tools.sh rebuilds compiled AgentCanon tools after safe updates.
# downstream implementation ./agent_tools/agent_canon_update_todos.py advances parent-repo AgentCanon update TODO state after safe updates.
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
  bash tools/update_agent_canon.sh latest [branch]
  bash tools/update_agent_canon.sh apply [branch]
  bash tools/update_agent_canon.sh rebuild-tools
  bash tools/update_agent_canon.sh merge-main-into-current [branch]
  bash tools/update_agent_canon.sh status

Commands:
  plan
      Print the AgentCanon update route for the current parent repo.
  latest
      Tool-first update workflow. It applies a safe AgentCanon main update,
      repairs root views, writes/acknowledges parent update TODO state when
      possible, and emits a machine-readable Agent workflow route when local
      shared-canon work or merge conflicts require human/agent resolution.
  apply
      Update the parent repo to AgentCanon main when the update surface is safe.
  rebuild-tools
      Rebuild compiled AgentCanon tools from the currently checked-out source.
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

emit_remote_main_ancestor_evidence() {
  local remote_sha="$1"
  local post_head="$2"

  if git -C "$ROOT_DIR/$PREFIX" merge-base --is-ancestor "$remote_sha" "$post_head"; then
    echo "agent_canon_merge_remote_main_in_post_head=yes"
    echo "agent_canon_merge_remote_main_verified=yes"
    return
  fi
  echo "agent_canon_merge_remote_main_in_post_head=no"
  echo "agent_canon_merge_remote_main_verified=no"
  die "current AgentCanon branch does not contain fetched remote main after merge-main-into-current"
}

plan_value() {
  local key="$1"
  local text="$2"
  awk -F= -v key="$key" '$1 == key {print substr($0, index($0, "=") + 1); exit}' <<< "$text"
}

emit_agentcanon_conflict_workflow_route() {
  local reason="$1"
  echo "AGENT_CANON_LATEST_TOOL_RESULT=agent_workflow_required"
  echo "AGENT_CANON_LATEST_BLOCK_REASON=$reason"
  echo "AGENT_CANON_LATEST_WORKFLOW=agents/workflows/derived-agent-canon-diff-workflow.md"
  echo "AGENT_CANON_LATEST_CONFLICT_COMMAND=bash tools/update_agent_canon.sh merge-main-into-current"
  echo "AGENT_CANON_LATEST_POST_MERGE_COMMAND=make agent-canon-ensure-latest"
  echo "NEXT_ACTION=run_agentcanon_conflict_workflow"
}

route_requires_agent_workflow() {
  local route="$1"
  local prefix_mode="$2"
  local dirty_update_surface="$3"
  local submodule_worktree_status="$4"

  case "$route" in
    local_contains_remote|diverged_submodule_history|diverged_local_history|snapshot_import_unsafe_tree_not_in_remote)
      return 0
      ;;
    deferred_branch_pr)
      return 1
      ;;
  esac
  if [ "$prefix_mode" = "submodule" ] && [ "$submodule_worktree_status" = "dirty" ]; then
    return 0
  fi
  if [ "$dirty_update_surface" = "yes" ]; then
    case "$route" in
      submodule_update)
        return 1
        ;;
      *)
        return 0
        ;;
    esac
  fi
  return 1
}

acknowledge_update_todos_if_available() {
  local todo_tool="$ROOT_DIR/tools/agent_tools/agent_canon_update_todos.py"
  local state_path="$ROOT_DIR/.agent-canon/update-state.toml"
  local todo_log=""
  local pending_count=""

  if [ ! -f "$todo_tool" ]; then
    echo "AGENT_CANON_LATEST_TODOS=skipped_missing_tool"
    return 0
  fi

  todo_log="$(mktemp)"
  if ! python3 "$todo_tool" plan --write >"$todo_log" 2>&1; then
    cat "$todo_log"
    rm -f "$todo_log"
    echo "AGENT_CANON_LATEST_TODOS=failed"
    echo "NEXT_ACTION=repair_agent_canon_update_todo_state_then_rerun_latest"
    return 1
  fi
  cat "$todo_log"
  pending_count="$(awk -F= '/^AGENT_CANON_UPDATE_TODO_PENDING_COUNT=/{print $2}' "$todo_log")"
  rm -f "$todo_log"

  if [ "${pending_count:-0}" != "0" ]; then
    echo "AGENT_CANON_LATEST_TODOS=pending"
    echo "AGENT_CANON_LATEST_TOOL_RESULT=todo_workflow_required"
    echo "NEXT_ACTION=apply_agent_canon_update_todos_then_rerun_latest"
    return 2
  fi

  python3 "$todo_tool" acknowledge
  if [ -f "$state_path" ]; then
    git -C "$ROOT_DIR" add "$state_path"
    if ! git -C "$ROOT_DIR" diff --cached --quiet -- "$state_path"; then
      git -C "$ROOT_DIR" commit -m "chore: acknowledge agent-canon update tasks"
      echo "AGENT_CANON_LATEST_TODOS=acknowledged_committed"
      return 0
    fi
  fi
  echo "AGENT_CANON_LATEST_TODOS=acknowledged_noop"
}

rebuild_agent_tools_if_available() {
  local rebuild_tool="$ROOT_DIR/tools/rebuild_agent_tools.sh"
  if [ ! -f "$rebuild_tool" ]; then
    echo "AGENT_CANON_TOOL_REBUILD=skipped_missing_tool"
    return
  fi
  bash "$rebuild_tool"
}

cmd_plan() {
  local branch="${1:-$DEFAULT_BRANCH}"
  bash "$ROOT_DIR/tools/sync_agent_canon.sh" plan "$branch"
}

cmd_latest() {
  local branch="${1:-$DEFAULT_BRANCH}"
  local plan_output=""
  local route=""
  local prefix_mode=""
  local dirty_update_surface=""
  local submodule_worktree_status=""
  local latest_log=""
  local latest_rc=0

  plan_output="$(cmd_plan "$branch")"
  printf '%s\n' "$plan_output"
  route="$(plan_value agent_canon_plan_route "$plan_output")"
  prefix_mode="$(plan_value agent_canon_plan_prefix_mode "$plan_output")"
  dirty_update_surface="$(plan_value agent_canon_plan_dirty_update_surface "$plan_output")"
  submodule_worktree_status="$(plan_value agent_canon_plan_submodule_worktree_status "$plan_output")"

  if route_requires_agent_workflow "$route" "$prefix_mode" "$dirty_update_surface" "$submodule_worktree_status"; then
    emit_agentcanon_conflict_workflow_route "route=${route:-unknown};dirty_update_surface=${dirty_update_surface:-unknown};submodule_worktree_status=${submodule_worktree_status:-unknown}"
    return 2
  fi

  latest_log="$(mktemp)"
  bash "$ROOT_DIR/tools/sync_agent_canon.sh" ensure-latest "$branch" >"$latest_log" 2>&1 || latest_rc=$?
  if [ "$latest_rc" -ne 0 ]; then
    cat "$latest_log"
    rm -f "$latest_log"
    emit_agentcanon_conflict_workflow_route "ensure_latest_failed=$latest_rc;route=${route:-unknown}"
    return "$latest_rc"
  fi
  cat "$latest_log"
  if grep -q '^agent_canon_latest=deferred_branch_pr$' "$latest_log"; then
    rm -f "$latest_log"
    bash "$ROOT_DIR/tools/sync_agent_canon.sh" check
    echo "AGENT_CANON_LATEST_TOOL_RESULT=deferred_branch_pr"
    echo "NEXT_ACTION=after_agentcanon_PR_merge_rerun_make_agent-canon-ensure-latest"
    return 0
  fi
  rm -f "$latest_log"

  bash "$ROOT_DIR/tools/sync_agent_canon.sh" check
  rebuild_agent_tools_if_available
  acknowledge_update_todos_if_available || return $?
  echo "AGENT_CANON_LATEST_TOOL_RESULT=updated"
  echo "NEXT_ACTION=run_validation_then_push_parent_repo"
}

cmd_apply() {
  local branch="${1:-$DEFAULT_BRANCH}"
  local latest_log=""
  local latest_rc=0

  latest_log="$(mktemp)"
  bash "$ROOT_DIR/tools/sync_agent_canon.sh" ensure-latest "$branch" >"$latest_log" 2>&1 || latest_rc=$?
  cat "$latest_log"
  if [ "$latest_rc" -ne 0 ]; then
    rm -f "$latest_log"
    return "$latest_rc"
  fi
  if grep -q '^agent_canon_latest=deferred_branch_pr$' "$latest_log"; then
    rm -f "$latest_log"
    echo "AGENT_CANON_TOOL_REBUILD=skipped_deferred_branch_pr"
    return 0
  fi
  rm -f "$latest_log"
  rebuild_agent_tools_if_available
}

cmd_rebuild_tools() {
  rebuild_agent_tools_if_available
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
    echo "NEXT_ACTION=commit_agentcanon_artifacts_or_explicitly_stash_non_artifact_changes_then_rerun_merge-main-into-current"
    die "submodule '$PREFIX' has uncommitted changes; commit AgentCanon-owned artifacts or explicitly stash non-artifact local changes before merging main"
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
    emit_remote_main_ancestor_evidence "$remote_sha" "$pre_head"
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
    emit_remote_main_ancestor_evidence "$remote_sha" "$pre_head"
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
    emit_remote_main_ancestor_evidence "$remote_sha" "$post_head"
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
    latest)
      shift
      cmd_latest "${1:-$DEFAULT_BRANCH}"
      ;;
    apply)
      shift
      cmd_apply "${1:-$DEFAULT_BRANCH}"
      ;;
    rebuild-tools)
      shift
      cmd_rebuild_tools
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
