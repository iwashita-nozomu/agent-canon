#!/usr/bin/env bash
# @dependency-start
# contract tool
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
  bash tools/update_agent_canon.sh merge-main-into-current-preserve-dirty [branch]
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
  merge-main-into-current-preserve-dirty
      Explicitly stash dirty vendor/agent-canon work, run merge-main-into-current,
      and restore the dirty work after a successful merge. If the merge itself
      conflicts, the stash is kept and the command reports the stash ref to
      restore after resolving the main merge.
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

parent_repo_log_slug() {
  local raw="${AGENT_CANON_LOG_REPO_SLUG:-}"
  if [ -z "$raw" ]; then
    raw="$(basename "$ROOT_DIR")"
  fi
  sanitize_ref_component "$raw"
}

status_porcelain_path() {
  local line="$1"
  local path="${line:3}"
  case "$path" in
    *" -> "*)
      path="${path##* -> }"
      ;;
  esac
  printf '%s\n' "$path"
}

is_accumulated_eval_result_path() {
  case "$1" in
    agents/evals/results/*)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

is_jsonl_eval_result_path() {
  case "$1" in
    agents/evals/results/*.jsonl|agents/evals/results/*/*.jsonl|agents/evals/results/*/*/*.jsonl|agents/evals/results/*/*/*/*.jsonl)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

restore_original_submodule_ref() {
  local original_branch="$1"
  local original_head="$2"
  if [ -n "$original_branch" ]; then
    git -C "$ROOT_DIR/$PREFIX" switch "$original_branch" >/dev/null
    return
  fi
  git -C "$ROOT_DIR/$PREFIX" checkout --detach "$original_head" >/dev/null
}

stash_ref_for_sha() {
  local stash_sha="$1"
  git -C "$ROOT_DIR/$PREFIX" stash list --format='%gd %H' \
    | awk -v sha="$stash_sha" '$2 == sha {print $1; exit}'
}

drop_stash_sha_if_present() {
  local stash_sha="$1"
  local stash_ref=""
  stash_ref="$(stash_ref_for_sha "$stash_sha")"
  [ -n "$stash_ref" ] || return 0
  git -C "$ROOT_DIR/$PREFIX" stash drop "$stash_ref" >/dev/null
}

remove_eval_log_worktree() {
  local worktree_path="$1"
  local branch="$2"
  if [ -n "$worktree_path" ] && [ -d "$worktree_path" ]; then
    git -C "$ROOT_DIR/$PREFIX" worktree remove --force "$worktree_path" >/dev/null 2>&1 || true
  fi
  if [ -n "$branch" ]; then
    git -C "$ROOT_DIR/$PREFIX" branch -D "$branch" >/dev/null 2>&1 || true
  fi
}

resolve_eval_jsonl_conflicts() {
  local worktree_root="$1"
  local conflict_path=""
  local tmp_dir=""
  local unresolved=""

  while IFS= read -r conflict_path; do
    [ -n "$conflict_path" ] || continue
    if ! is_jsonl_eval_result_path "$conflict_path"; then
      echo "AGENT_CANON_EVAL_LOG_PARK_CONFLICT_UNSAFE=$conflict_path"
      return 1
    fi
    tmp_dir="$(mktemp -d)"
    git -C "$worktree_root" show ":2:$conflict_path" >"$tmp_dir/ours.jsonl" 2>/dev/null || true
    git -C "$worktree_root" show ":3:$conflict_path" >"$tmp_dir/theirs.jsonl" 2>/dev/null || true
    mkdir -p "$(dirname "$worktree_root/$conflict_path")"
    awk 'NF && !seen[$0]++ { print }' "$tmp_dir/ours.jsonl" "$tmp_dir/theirs.jsonl" >"$worktree_root/$conflict_path"
    rm -rf "$tmp_dir"
    git -C "$worktree_root" add "$conflict_path"
  done < <(git -C "$worktree_root" diff --name-only --diff-filter=U)

  unresolved="$(git -C "$worktree_root" diff --name-only --diff-filter=U)"
  [ -z "$unresolved" ]
}

park_eval_log_dirty_state_if_safe() {
  local status_output=""
  local line=""
  local path=""
  local current_branch=""
  local current_head=""
  local log_branch=""
  local log_start_ref=""
  local stash_sha=""
  local apply_log=""
  local apply_rc=0
  local commit_sha=""
  local tmp_worktree=""
  local tmp_branch=""
  local -a paths=()

  ensure_agent_canon_submodule
  status_output="$(git -C "$ROOT_DIR/$PREFIX" status --porcelain=v1 --untracked-files=all)"
  if [ -z "$status_output" ]; then
    echo "AGENT_CANON_EVAL_LOG_PARK=clean"
    return 0
  fi

  while IFS= read -r line; do
    [ -n "$line" ] || continue
    path="$(status_porcelain_path "$line")"
    if ! is_accumulated_eval_result_path "$path"; then
      echo "AGENT_CANON_EVAL_LOG_PARK=skipped_non_log_dirty"
      echo "AGENT_CANON_EVAL_LOG_PARK_BLOCKING_PATH=$path"
      return 1
    fi
    paths+=("$path")
  done <<< "$status_output"

  current_branch="$(git -C "$ROOT_DIR/$PREFIX" symbolic-ref --quiet --short HEAD 2>/dev/null || true)"
  current_head="$(git -C "$ROOT_DIR/$PREFIX" rev-parse HEAD)"
  log_branch="${AGENT_CANON_EVAL_LOG_BRANCH:-agent-logs/$(parent_repo_log_slug)}"
  tmp_branch="agent-log-park/$(parent_repo_log_slug)/$(date -u +%Y%m%dT%H%M%SZ)-$$"

  echo "AGENT_CANON_EVAL_LOG_PARK=started"
  echo "AGENT_CANON_EVAL_LOG_PARK_BRANCH=$log_branch"
  git -C "$ROOT_DIR/$PREFIX" stash push -u -m "park eval logs before AgentCanon latest" -- "${paths[@]}" >/dev/null
  stash_sha="$(git -C "$ROOT_DIR/$PREFIX" rev-parse --verify refs/stash)"

  git -C "$ROOT_DIR/$PREFIX" fetch origin "$log_branch" >/dev/null 2>&1 || true
  if git -C "$ROOT_DIR/$PREFIX" show-ref --verify --quiet "refs/remotes/origin/$log_branch"; then
    log_start_ref="origin/$log_branch"
  elif git -C "$ROOT_DIR/$PREFIX" show-ref --verify --quiet "refs/heads/$log_branch"; then
    log_start_ref="$log_branch"
  else
    log_start_ref="$current_head"
  fi
  tmp_worktree="$(mktemp -d)"
  git -C "$ROOT_DIR/$PREFIX" worktree add -b "$tmp_branch" "$tmp_worktree" "$log_start_ref" >/dev/null

  apply_log="$(mktemp)"
  git -C "$tmp_worktree" stash apply "$stash_sha" >"$apply_log" 2>&1 || apply_rc=$?
  if [ "$apply_rc" -ne 0 ]; then
    if ! resolve_eval_jsonl_conflicts "$tmp_worktree"; then
      cat "$apply_log" >&2
      rm -f "$apply_log"
      remove_eval_log_worktree "$tmp_worktree" "$tmp_branch"
      return "$apply_rc"
    fi
  fi
  rm -f "$apply_log"

  git -C "$tmp_worktree" add -- "${paths[@]}"
  if git -C "$tmp_worktree" diff --cached --quiet; then
    echo "AGENT_CANON_EVAL_LOG_PARK=noop"
    drop_stash_sha_if_present "$stash_sha"
    remove_eval_log_worktree "$tmp_worktree" "$tmp_branch"
    return 0
  fi
  git -C "$tmp_worktree" \
    -c user.name="${GIT_AUTHOR_NAME:-AgentCanon Log Park}" \
    -c user.email="${GIT_AUTHOR_EMAIL:-agent-canon-log@example.invalid}" \
    commit -m "Append $(parent_repo_log_slug) AgentCanon eval logs" >/dev/null
  commit_sha="$(git -C "$tmp_worktree" rev-parse HEAD)"
  git -C "$tmp_worktree" push -u origin "HEAD:refs/heads/$log_branch" >/dev/null
  drop_stash_sha_if_present "$stash_sha"
  remove_eval_log_worktree "$tmp_worktree" "$tmp_branch"
  echo "AGENT_CANON_EVAL_LOG_PARK=committed"
  echo "AGENT_CANON_EVAL_LOG_PARK_COMMIT=$commit_sha"
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
  echo "AGENT_CANON_LATEST_CONFLICT_COMMAND=bash tools/update_agent_canon.sh merge-main-into-current-preserve-dirty"
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
      already_current_submodule|local_tree_matches_remote|submodule_update)
        return 1
        ;;
      *)
        return 0
        ;;
    esac
  fi
  return 1
}

can_preserve_dirty_agentcanon_latest() {
  local route="$1"
  local prefix_mode="$2"
  local submodule_worktree_status="$3"

  [ "$prefix_mode" = "submodule" ] || return 1
  [ "$submodule_worktree_status" = "dirty" ] || return 1
  case "$route" in
    already_current_submodule|submodule_update|local_contains_remote|diverged_submodule_history|diverged_local_history|deferred_branch_pr)
      return 0
      ;;
  esac
  return 1
}

preserve_dirty_agentcanon_latest() {
  local branch="$1"
  local route="$2"
  local preserve_rc=0

  echo "AGENT_CANON_LATEST_DIRTY_PRESERVE=started"
  echo "AGENT_CANON_LATEST_DIRTY_PRESERVE_ROUTE=${route:-unknown}"
  cmd_merge_main_into_current_preserve_dirty "$branch" || preserve_rc=$?
  if [ "$preserve_rc" -ne 0 ]; then
    echo "AGENT_CANON_LATEST_DIRTY_PRESERVE=failed"
    echo "AGENT_CANON_LATEST_TOOL_RESULT=dirty_preserve_failed"
    return "$preserve_rc"
  fi
  echo "AGENT_CANON_LATEST_DIRTY_PRESERVE=pass"
  if ! bash "$ROOT_DIR/tools/sync_agent_canon.sh" link-root; then
    echo "AGENT_CANON_LATEST_ROOT_VIEW_REPAIR=failed"
    echo "AGENT_CANON_LATEST_TOOL_RESULT=dirty_preserve_root_view_repair_failed"
    echo "NEXT_ACTION=commit_or_stash_agentcanon_root_view_changes_then_rerun_make_agent-canon-ensure-latest"
    return 1
  fi
  echo "AGENT_CANON_LATEST_ROOT_VIEW_REPAIR=pass"
  if ! bash "$ROOT_DIR/tools/sync_agent_canon.sh" check; then
    echo "AGENT_CANON_LATEST_SHARED_SURFACE_CHECK=failed"
    echo "AGENT_CANON_LATEST_TOOL_RESULT=dirty_preserve_shared_surface_check_failed"
    echo "NEXT_ACTION=repair_shared_surface_with_link-root_then_rerun_make_agent-canon-ensure-latest"
    return 1
  fi
  echo "AGENT_CANON_LATEST_SHARED_SURFACE_CHECK=pass"
  echo "AGENT_CANON_LATEST_TOOL_RESULT=agent_workflow_preserved_dirty"
  echo "AGENT_CANON_LATEST_WORKFLOW=agents/workflows/derived-agent-canon-diff-workflow.md"
  echo "AGENT_CANON_LATEST_POST_MERGE_COMMAND=make agent-canon-ensure-latest"
  echo "NEXT_ACTION=continue_agentcanon_branch_PR_flow_with_restored_dirty_state"
  return 0
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
    echo "AGENT_CANON_LATEST_TOOL_RESULT=updated_with_pending_todos"
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
  local park_rc=0
  local todo_rc=0

  park_eval_log_dirty_state_if_safe || park_rc=$?
  if [ "$park_rc" -gt 1 ]; then
    echo "AGENT_CANON_LATEST_TOOL_RESULT=eval_log_park_failed"
    echo "NEXT_ACTION=repair_eval_log_branch_then_rerun_latest"
    return "$park_rc"
  fi

  plan_output="$(cmd_plan "$branch")"
  printf '%s\n' "$plan_output"
  route="$(plan_value agent_canon_plan_route "$plan_output")"
  prefix_mode="$(plan_value agent_canon_plan_prefix_mode "$plan_output")"
  dirty_update_surface="$(plan_value agent_canon_plan_dirty_update_surface "$plan_output")"
  submodule_worktree_status="$(plan_value agent_canon_plan_submodule_worktree_status "$plan_output")"

  if route_requires_agent_workflow "$route" "$prefix_mode" "$dirty_update_surface" "$submodule_worktree_status"; then
    if can_preserve_dirty_agentcanon_latest "$route" "$prefix_mode" "$submodule_worktree_status"; then
      preserve_dirty_agentcanon_latest "$branch" "$route"
      return $?
    fi
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
  if [ "$prefix_mode" = "submodule" ] && ! grep -q '^agent_canon_latest_submodule_local_state_checked=yes$' "$latest_log"; then
    rm -f "$latest_log"
    emit_agentcanon_conflict_workflow_route "ensure_latest_missing_submodule_local_state_evidence=yes;route=${route:-unknown}"
    return 2
  fi
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
  acknowledge_update_todos_if_available || todo_rc=$?
  if [ "$todo_rc" -eq 2 ]; then
    return 0
  fi
  if [ "$todo_rc" -ne 0 ]; then
    return "$todo_rc"
  fi
  echo "AGENT_CANON_LATEST_TOOL_RESULT=updated"
  echo "NEXT_ACTION=run_validation_then_push_parent_repo"
}

cmd_apply() {
  local branch="${1:-$DEFAULT_BRANCH}"
  local latest_log=""
  local latest_rc=0
  local park_rc=0

  park_eval_log_dirty_state_if_safe || park_rc=$?
  if [ "$park_rc" -gt 1 ]; then
    echo "AGENT_CANON_LATEST_TOOL_RESULT=eval_log_park_failed"
    echo "NEXT_ACTION=repair_eval_log_branch_then_rerun_latest"
    return "$park_rc"
  fi

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
    echo "NEXT_ACTION=commit_agentcanon_artifacts_or_rerun_merge-main-into-current-preserve-dirty"
    die "submodule '$PREFIX' has uncommitted changes; commit AgentCanon-owned artifacts or use merge-main-into-current-preserve-dirty before merging main"
  fi
  echo "agent_canon_merge_worktree_status=clean"

  if [ -z "$current_branch" ]; then
    echo "agent_canon_merge_result=blocked_detached_head"
    echo "agent_canon_parent_pin_pending=$(parent_pin_pending "$pre_head")"
    echo "NEXT_ACTION=create_agentcanon_branch_then_rerun_merge-main-into-current-preserve-dirty"
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

cmd_merge_main_into_current_preserve_dirty() {
  local branch="${1:-$DEFAULT_BRANCH}"
  local current_branch=""
  local submodule_status=""
  local stash_sha=""
  local stash_ref=""
  local merge_rc=0
  local restore_log=""
  local restore_rc=0

  ensure_agent_canon_submodule
  current_branch="$(git -C "$ROOT_DIR/$PREFIX" symbolic-ref --quiet --short HEAD 2>/dev/null || true)"
  submodule_status="$(git -C "$ROOT_DIR/$PREFIX" status --short --untracked-files=all)"

  echo "agent_canon_merge_dirty_preserve_prefix=$PREFIX"
  echo "agent_canon_merge_dirty_preserve_target_branch=${current_branch:-<detached>}"

  if [ -z "$current_branch" ]; then
    echo "agent_canon_merge_dirty_preserve_result=blocked_detached_head"
    echo "agent_canon_merge_dirty_preserve_worktree_status=$([ -n "$submodule_status" ] && echo dirty || echo clean)"
    echo "NEXT_ACTION=create_agentcanon_branch_then_rerun_merge-main-into-current-preserve-dirty"
    die "submodule '$PREFIX' is detached; create or switch to a branch before preserving dirty state and merging main"
  fi

  if [ -z "$submodule_status" ]; then
    echo "agent_canon_merge_dirty_preserve_result=clean_passthrough"
    cmd_merge_main_into_current "$branch"
    return
  fi

  echo "agent_canon_merge_dirty_preserve_result=started"
  echo "agent_canon_merge_dirty_preserve_worktree_status=dirty"
  git -C "$ROOT_DIR/$PREFIX" stash push -u -m "preserve dirty AgentCanon work before merge-main-into-current" >/dev/null
  stash_sha="$(git -C "$ROOT_DIR/$PREFIX" rev-parse --verify refs/stash)"
  stash_ref="$(stash_ref_for_sha "$stash_sha")"
  echo "agent_canon_merge_dirty_stash_ref=${stash_ref:-<unknown>}"
  echo "agent_canon_merge_dirty_stash_sha=$stash_sha"

  ( cmd_merge_main_into_current "$branch" ) || merge_rc=$?
  if [ "$merge_rc" -ne 0 ]; then
    echo "agent_canon_merge_dirty_restore=skipped_merge_failed"
    echo "agent_canon_merge_dirty_stash_kept=${stash_ref:-$stash_sha}"
    echo "NEXT_ACTION=resolve_agentcanon_merge_then_apply_stash_ref_${stash_ref:-$stash_sha}"
    return "$merge_rc"
  fi

  restore_log="$(mktemp)"
  git -C "$ROOT_DIR/$PREFIX" stash apply "$stash_sha" >"$restore_log" 2>&1 || restore_rc=$?
  if [ "$restore_rc" -eq 0 ]; then
    rm -f "$restore_log"
    drop_stash_sha_if_present "$stash_sha"
    echo "agent_canon_merge_dirty_restore=applied"
    echo "agent_canon_merge_dirty_stash_dropped=yes"
    echo "NEXT_ACTION=review_restored_dirty_state_then_continue_agentcanon_PR_flow"
    return
  fi

  cat "$restore_log" >&2
  rm -f "$restore_log"
  echo "agent_canon_merge_dirty_restore=conflict"
  echo "agent_canon_merge_dirty_stash_kept=${stash_ref:-$stash_sha}"
  echo "NEXT_ACTION=resolve_restored_dirty_conflicts_then_drop_stash_ref_${stash_ref:-$stash_sha}"
  return "$restore_rc"
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
    merge-main-into-current-preserve-dirty)
      shift
      cmd_merge_main_into_current_preserve_dirty "${1:-$DEFAULT_BRANCH}"
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
