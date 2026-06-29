#!/usr/bin/env bash
# @dependency-start
# contract tool
# responsibility Provides sync agent canon repository automation.
# upstream design ../documents/SHARED_RUNTIME_SURFACES.md shared surface ownership policy
# upstream design ../documents/shared-runtime-surfaces.toml machine-readable surface manifest
# upstream implementation ./agent_tools/surface_manifest.py renders link, copy, regular, and root-absent specs
# downstream implementation ../tests/tools/test_update_agent_canon.py verifies sync/update behavior
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
REMOTE_NAME="${AGENT_CANON_REMOTE_NAME:-agent-canon}"
DEFAULT_BRANCH="${AGENT_CANON_BRANCH:-main}"
FORCE_RELINK="${AGENT_CANON_FORCE_RELINK:-0}"
PLAN_REMOTE_OVERRIDE_URL="${AGENT_CANON_PLAN_REMOTE_URL:-}"
CANONICAL_AGENT_CANON_REMOTE_URL="${AGENT_CANON_GITHUB_REMOTE_URL:-https://github.com/iwashita-nozomu/agent-canon.git}"
SURFACE_MANIFEST="${AGENT_CANON_SURFACE_MANIFEST:-documents/shared-runtime-surfaces.toml}"

usage() {
  cat <<EOF
Usage:
  bash tools/sync_agent_canon.sh plan [branch]
  bash tools/sync_agent_canon.sh link-root
  bash tools/sync_agent_canon.sh check
  bash tools/sync_agent_canon.sh submodule-add <remote-url> [branch]
  bash tools/sync_agent_canon.sh ensure-latest [branch]
  bash tools/sync_agent_canon.sh status

Legacy subtree / snapshot / direct push routes are compatibility-only and are
not listed as user-facing commands. Use tools/update_agent_canon.sh for normal
GitHub/submodule-first parent repo updates.

Environment overrides:
  AGENT_CANON_PREFIX
  AGENT_CANON_REMOTE_NAME
  AGENT_CANON_REMOTE_URL
  AGENT_CANON_GITHUB_REMOTE_URL
  AGENT_CANON_BRANCH
  AGENT_CANON_FORCE_RELINK=1
EOF
}

die() {
  echo "sync_agent_canon.sh: $*" >&2
  exit 1
}

require_git_repo() {
  git -C "$ROOT_DIR" rev-parse --show-toplevel >/dev/null 2>&1 || die "repository root not found"
}

require_clean_worktree() {
  if [ -n "$(git -C "$ROOT_DIR" status --short)" ]; then
    die "worktree is dirty; commit required artifacts or explicitly stash non-artifact local changes before AgentCanon operations"
  fi
}

refresh_git_index_for_paths() {
  local -a paths=("$@")
  [ "${#paths[@]}" -gt 0 ] || return
  git -C "$ROOT_DIR" update-index -q --refresh -- "${paths[@]}" >/dev/null 2>&1 || true
}

agent_canon_update_surface_status() {
  local -a paths=("$PREFIX" ".gitmodules")
  local spec=""

  while IFS= read -r spec; do
    [ -n "$spec" ] || continue
    paths+=("${spec%%:*}")
  done < <(
    {
      build_link_specs
      build_copy_specs
    }
  )
  while IFS= read -r spec; do
    [ -n "$spec" ] || continue
    paths+=("$spec")
  done < <(build_root_absent_paths)

  refresh_git_index_for_paths "${paths[@]}"
  git -C "$ROOT_DIR" status --short --untracked-files=all -- "${paths[@]}"
  if is_submodule_prefix && git -C "$ROOT_DIR/$PREFIX" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    git -C "$ROOT_DIR/$PREFIX" status --short --untracked-files=all
  fi
}

ensure_remote() {
  local remote_url="$1"
  if git -C "$ROOT_DIR" remote get-url "$REMOTE_NAME" >/dev/null 2>&1; then
    return
  fi
  git -C "$ROOT_DIR" remote add "$REMOTE_NAME" "$remote_url"
}

require_existing_remote() {
  git -C "$ROOT_DIR" remote get-url "$REMOTE_NAME" >/dev/null 2>&1 || die "remote '$REMOTE_NAME' is not configured"
}

default_remote_url() {
  if [ -n "${AGENT_CANON_REMOTE_URL:-}" ]; then
    echo "$AGENT_CANON_REMOTE_URL"
    return
  fi
  echo "$CANONICAL_AGENT_CANON_REMOTE_URL"
  return 0
}

ensure_existing_remote_or_default() {
  local remote_url=""
  if git -C "$ROOT_DIR" remote get-url "$REMOTE_NAME" >/dev/null 2>&1; then
    return
  fi
  remote_url="$(default_remote_url)"
  if [ -z "$remote_url" ]; then
    die "remote '$REMOTE_NAME' is not configured; set AGENT_CANON_REMOTE_URL or run 'git remote add $REMOTE_NAME <agent-canon-url>'"
  fi
  git -C "$ROOT_DIR" remote add "$REMOTE_NAME" "$remote_url"
  echo "agent_canon_remote_added=$remote_url"
}

ensure_prefix_exists() {
  [ -d "$ROOT_DIR/$PREFIX" ] || die "prefix '$PREFIX' does not exist"
}

prefix_git_mode() {
  git -C "$ROOT_DIR" ls-tree HEAD "$PREFIX" 2>/dev/null | awk '{print $1}'
}

is_submodule_prefix() {
  [ "$(prefix_git_mode)" = "160000" ]
}

submodule_commit() {
  git -C "$ROOT_DIR" rev-parse "HEAD:$PREFIX"
}

submodule_remote_url() {
  git -C "$ROOT_DIR" config -f .gitmodules --get "submodule.${PREFIX}.url" 2>/dev/null || true
}

submodule_pushed_branch_ref() {
  local commit="$1"
  local current_branch=""
  local upstream_ref=""
  local remote_ref=""
  local remote_branch=""
  local remote_commit=""
  local display_branch=""

  current_branch="$(git -C "$ROOT_DIR/$PREFIX" symbolic-ref --quiet --short HEAD 2>/dev/null || true)"

  if [ -n "$current_branch" ] && [ "$current_branch" != "$DEFAULT_BRANCH" ]; then
    upstream_ref="$(git -C "$ROOT_DIR/$PREFIX" for-each-ref --format='%(upstream:short)' "refs/heads/$current_branch" 2>/dev/null || true)"
  fi
  if [ -n "${upstream_ref:-}" ]; then
    remote_commit="$(git -C "$ROOT_DIR/$PREFIX" rev-parse --verify "$upstream_ref^{commit}" 2>/dev/null || true)"
    if [ "$remote_commit" = "$commit" ]; then
      echo "$current_branch:$upstream_ref"
      return 0
    fi
  fi

  while IFS= read -r remote_ref; do
    [ -n "$remote_ref" ] || continue
    case "$remote_ref" in
      */HEAD)
        continue
        ;;
    esac
    remote_branch="${remote_ref#*/}"
    [ "$remote_branch" != "$DEFAULT_BRANCH" ] || continue
    remote_commit="$(git -C "$ROOT_DIR/$PREFIX" rev-parse --verify "$remote_ref^{commit}" 2>/dev/null || true)"
    if [ "$remote_commit" = "$commit" ]; then
      display_branch="${current_branch:-$remote_branch}"
      [ "$display_branch" != "$DEFAULT_BRANCH" ] || display_branch="$remote_branch"
      echo "$display_branch:$remote_ref"
      return 0
    fi
  done < <(git -C "$ROOT_DIR/$PREFIX" for-each-ref --format='%(refname:short)' refs/remotes 2>/dev/null || true)

  return 1
}

submodule_deferred_branch_pr_ref() {
  local commit="$1"
  local worktree_head="$2"
  local worktree_status="$3"

  [ "$worktree_head" = "$commit" ] || return 1
  [ "$worktree_status" = "clean" ] || return 1
  submodule_pushed_branch_ref "$commit"
}

ensure_submodule_checkout() {
  if git -C "$ROOT_DIR/$PREFIX" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    return
  fi
  git -C "$ROOT_DIR" submodule update --init --recursive "$PREFIX" >/dev/null
}

build_link_specs() {
  python3 "$ROOT_DIR/$PREFIX/tools/agent_tools/surface_manifest.py" \
    --root "$ROOT_DIR" --prefix "$PREFIX" --manifest "$SURFACE_MANIFEST" link-specs
}

build_regular_specs() {
  python3 "$ROOT_DIR/$PREFIX/tools/agent_tools/surface_manifest.py" \
    --root "$ROOT_DIR" --prefix "$PREFIX" --manifest "$SURFACE_MANIFEST" regular-specs
}

repo_local_goal_template() {
  cat <<'EOF'
# Goal
<!--
@dependency-start
responsibility Defines this repository's local goal loop contract.
upstream design README.md repository entrypoint
upstream implementation tools/agent_tools/goal_loop.py consumes this contract
@dependency-end
-->

## Loop Contract

- goal_status: achieved
- run_safety_cap: 0
- current_iteration: 0
- active_run_id:
- stop_reason: no active repo-local goal

## Objective

No active repo-local goal is set.

## Exit Criteria

- [x] G0: No active repo-local goal is pending.

## Backlog

## Loop Log

- initialized repo-local placeholder goal.
EOF
}

ensure_repo_local_goal() {
  local path="$ROOT_DIR/goal.md"
  local target=""
  if [ -L "$path" ]; then
    target="$(readlink "$path")"
    case "$target" in
      "$PREFIX"/*|./"$PREFIX"/*|../"$PREFIX"/*|*"$PREFIX"/goal.md)
        rm -f "$path"
        repo_local_goal_template >"$path"
        echo "goal_md=converted_from_shared_symlink"
        ;;
    esac
  elif [ ! -e "$path" ]; then
    repo_local_goal_template >"$path"
    echo "goal_md=created_repo_local_placeholder"
  fi
}

goal_is_shared_symlink() {
  local path="$ROOT_DIR/goal.md"
  local target=""
  [ -L "$path" ] || return 1
  target="$(readlink "$path")"
  case "$target" in
    "$PREFIX"/*|./"$PREFIX"/*|../"$PREFIX"/*|*"$PREFIX"/goal.md)
      return 0
      ;;
  esac
  return 1
}

build_removed_legacy_paths() {
  python3 "$ROOT_DIR/$PREFIX/tools/agent_tools/surface_manifest.py" \
    --root "$ROOT_DIR" --prefix "$PREFIX" --manifest "$SURFACE_MANIFEST" removed-legacy-paths
}

build_root_absent_paths() {
  python3 "$ROOT_DIR/$PREFIX/tools/agent_tools/surface_manifest.py" \
    --root "$ROOT_DIR" --prefix "$PREFIX" --manifest "$SURFACE_MANIFEST" root-absent-paths
}

build_copy_specs() {
  python3 "$ROOT_DIR/$PREFIX/tools/agent_tools/surface_manifest.py" \
    --root "$ROOT_DIR" --prefix "$PREFIX" --manifest "$SURFACE_MANIFEST" copy-specs
}

link_path() {
  local path="$1"
  local target="$2"
  local abs_path="$ROOT_DIR/$path"
  rm -rf "$abs_path"
  mkdir -p "$(dirname "$abs_path")"
  ln -s "$target" "$abs_path"
}

copy_path() {
  local path="$1"
  local source="$2"
  local abs_path="$ROOT_DIR/$path"
  local abs_source="$ROOT_DIR/$source"
  [ -e "$abs_source" ] || die "copy source '$source' does not exist"
  rm -rf "$abs_path"
  mkdir -p "$(dirname "$abs_path")"
  cp "$abs_source" "$abs_path"
}

regular_path() {
  local path="$1"
  local source="${2:-}"
  local abs_path="$ROOT_DIR/$path"
  local abs_source=""
  if [ -e "$abs_path" ] && [ ! -L "$abs_path" ]; then
    return
  fi
  [ -n "$source" ] || die "regular path '$path' is missing or is a symlink and has no seed source"
  abs_source="$ROOT_DIR/$source"
  [ -e "$abs_source" ] || die "regular seed source '$source' does not exist"
  rm -rf "$abs_path"
  mkdir -p "$(dirname "$abs_path")"
  cp -a "$abs_source" "$abs_path"
}

path_is_tracked() {
  local path="$1"
  git -C "$ROOT_DIR" ls-files --error-unmatch -- "$path" >/dev/null 2>&1
}

is_agentcanon_root_view_target() {
  local target="$1"
  case "$target" in
    "$PREFIX"|"$PREFIX"/*|"./$PREFIX"/*|"../$PREFIX"/*|"../../$PREFIX"/*|"../../../$PREFIX"/*|"../../../../$PREFIX"/*|"$ROOT_DIR/$PREFIX"|"$ROOT_DIR/$PREFIX"/*)
      return 0
      ;;
  esac
  return 1
}

root_view_symlink_candidate_paths() {
  git -C "$ROOT_DIR" ls-files -s | awk '$1 == "120000" {print $4}'
  while IFS= read -r path; do
    [ -n "$path" ] || continue
    [ -L "$ROOT_DIR/$path" ] || continue
    echo "$path"
  done < <(git -C "$ROOT_DIR" ls-files --others --exclude-standard --)
}

check_agentcanon_root_view_symlink_targets() {
  local path=""
  local target=""
  local abs_path=""
  local had_broken=0

  while IFS= read -r path; do
    [ -n "$path" ] || continue
    abs_path="$ROOT_DIR/$path"
    [ -L "$abs_path" ] || continue
    target="$(readlink "$abs_path")"
    is_agentcanon_root_view_target "$target" || continue
    if [ ! -e "$abs_path" ]; then
      echo "root-symlink[$path]=broken" >&2
      had_broken=1
    fi
  done < <(root_view_symlink_candidate_paths | sort -u)

  return "$had_broken"
}

ensure_surface_sync_safe() {
  local force="${1:-0}"
  local -a paths=()
  local status=""
  local spec=""

  if [ "$force" = "1" ] || [ "$FORCE_RELINK" = "1" ]; then
    return
  fi

  while IFS= read -r spec; do
    [ -n "$spec" ] || continue
    paths+=("${spec%%:*}")
  done < <(
    {
      build_link_specs
      build_copy_specs
    }
  )

  [ "${#paths[@]}" -gt 0 ] || return
  refresh_git_index_for_paths "${paths[@]}"
  status="$(git -C "$ROOT_DIR" status --short -- "${paths[@]}")"
  if [ -n "$status" ]; then
    echo "$status" >&2
    die "shared surface has uncommitted changes; commit required artifacts or explicitly stash non-artifact local changes first, or rerun with AGENT_CANON_FORCE_RELINK=1"
  fi
}

cmd_link_root() {
  local force="${1:-0}"
  ensure_prefix_exists
  ensure_surface_sync_safe "$force"

  local spec=""
  while IFS= read -r spec; do
    local path="${spec%%:*}"
    local target="${spec#*:}"
    link_path "$path" "$target"
  done < <(build_link_specs)

  while IFS= read -r spec; do
    local path="${spec%%:*}"
    local source="${spec#*:}"
    copy_path "$path" "$source"
  done < <(build_copy_specs)

  while IFS= read -r spec; do
    local path="${spec%%:*}"
    local source="${spec#*:}"
    regular_path "$path" "$source"
  done < <(build_regular_specs)

  while IFS= read -r path; do
    [ -n "$path" ] || continue
    rm -rf "$ROOT_DIR/$path"
  done < <(build_root_absent_paths)

  ensure_repo_local_goal
}

cmd_snapshot() {
  echo "agent_canon_snapshot_alias=deprecated_use_link_root"
  cmd_link_root
}

cmd_check() {
  ensure_prefix_exists

  local spec=""
  local failed=0

  while IFS= read -r spec; do
    local path="${spec%%:*}"
    local target="${spec#*:}"
    local abs_path="$ROOT_DIR/$path"
    if [ -L "$abs_path" ] && [ "$(readlink "$abs_path")" = "$target" ] && [ -e "$abs_path" ]; then
      continue
    fi
    if [ -L "$abs_path" ] && ! [ -e "$abs_path" ]; then
      echo "link[$path]=broken" >&2
    elif [ -e "$abs_path" ]; then
      echo "link[$path]=drift" >&2
    else
      echo "link[$path]=missing" >&2
    fi
    failed=1
  done < <(build_link_specs)

  while IFS= read -r spec; do
    local path="${spec%%:*}"
    local source="${spec#*:}"
    local abs_path="$ROOT_DIR/$path"
    local abs_source="$ROOT_DIR/$source"
    if [ -f "$abs_path" ] && [ -f "$abs_source" ] && cmp -s "$abs_path" "$abs_source"; then
      continue
    fi
    if [ -e "$abs_path" ]; then
      echo "copy[$path]=drift" >&2
    else
      echo "copy[$path]=missing" >&2
    fi
    failed=1
  done < <(build_copy_specs)

  while IFS= read -r spec; do
    local path="${spec%%:*}"
    local abs_path="$ROOT_DIR/$path"
    if [ -e "$abs_path" ] && [ ! -L "$abs_path" ]; then
      continue
    fi
    if [ -L "$abs_path" ]; then
      echo "regular[$path]=symlink" >&2
    else
      echo "regular[$path]=missing" >&2
    fi
    failed=1
  done < <(build_regular_specs)

  if ! python3 "$ROOT_DIR/$PREFIX/tools/agent_tools/surface_manifest.py" \
    --root "$ROOT_DIR" --prefix "$PREFIX" --manifest "$SURFACE_MANIFEST" check-doc >&2; then
    failed=1
  fi

  while IFS= read -r path; do
    [ -n "$path" ] || continue
    local abs_path="$ROOT_DIR/$path"
    if [ -e "$abs_path" ] || [ -L "$abs_path" ]; then
      echo "absent[$path]=present" >&2
      failed=1
    fi
  done < <(build_root_absent_paths)

  if goal_is_shared_symlink; then
    echo "goal.md=shared-symlink" >&2
    failed=1
  fi

  if ! check_agentcanon_root_view_symlink_targets; then
    failed=1
  fi

  if [ "$failed" -ne 0 ]; then
    die "shared surface drift detected; run 'bash tools/sync_agent_canon.sh link-root'"
  fi

  echo "shared surface is in sync"
}

stage_sync_paths() {
  local spec=""
  git -C "$ROOT_DIR" add -A -- "$PREFIX"

  while IFS= read -r spec; do
    [ -n "$spec" ] || continue
    git -C "$ROOT_DIR" add -A -- "${spec%%:*}"
  done < <(
    {
      build_link_specs
      build_copy_specs
    }
  )
  while IFS= read -r spec; do
    [ -n "$spec" ] || continue
    if [ -e "$ROOT_DIR/$spec" ] || [ -L "$ROOT_DIR/$spec" ] || path_is_tracked "$spec"; then
      git -C "$ROOT_DIR" add -A -- "$spec"
    fi
  done < <(build_root_absent_paths)
}

commit_sync_paths_if_needed() {
  local remote_sha="$1"
  local method="$2"

  stage_sync_paths
  if git -C "$ROOT_DIR" diff --cached --quiet; then
    return
  fi

  git -C "$ROOT_DIR" commit \
    -m "chore: sync agent-canon snapshot" \
    -m "agent-canon-remote: $remote_sha" \
    -m "agent-canon-update-method: $method" \
    -m "agent-canon-prefix: $PREFIX"
}

find_commit_by_tree() {
  local tree_sha="$1"
  local history_head="$2"
  local commit=""

  while IFS= read -r commit; do
    if [ "$(git -C "$ROOT_DIR" rev-parse "$commit^{tree}")" = "$tree_sha" ]; then
      echo "$commit"
      return
    fi
  done < <(git -C "$ROOT_DIR" rev-list "$history_head")

  return 1
}

find_submodule_commit_by_tree() {
  local tree_sha="$1"
  local history_head="$2"
  local commit=""

  while IFS= read -r commit; do
    if [ "$(git -C "$ROOT_DIR/$PREFIX" rev-parse "$commit^{tree}")" = "$tree_sha" ]; then
      echo "$commit"
      return
    fi
  done < <(git -C "$ROOT_DIR/$PREFIX" rev-list "$history_head")

  return 1
}

submodule_cherry_equivalent_to_remote() {
  local remote_sha="$1"
  local worktree_head="$2"
  local cherry_output=""

  cherry_output="$(git -C "$ROOT_DIR/$PREFIX" cherry "$remote_sha" "$worktree_head" 2>/dev/null || true)"
  if [ -z "$cherry_output" ]; then
    echo "yes"
    return
  fi
  if printf '%s\n' "$cherry_output" | grep -q '^+'; then
    echo "no"
    return
  fi
  echo "yes"
}

submodule_merge_conflicts() {
  local local_head="$1"
  local remote_sha="$2"

  if git -C "$ROOT_DIR/$PREFIX" merge-tree --write-tree "$local_head" "$remote_sha" >/dev/null 2>&1; then
    echo "no"
    return
  fi
  echo "yes"
}

materialize_cached_snapshot_diff() {
  local base_sha="$1"
  local remote_sha="$2"
  local status=""
  local path=""

  while IFS= read -r -d '' status && IFS= read -r -d '' path; do
    case "$status" in
      D)
        rm -f "$ROOT_DIR/$PREFIX/$path"
        ;;
      *)
        git -C "$ROOT_DIR" checkout-index -f -u -- "$PREFIX/$path"
        ;;
    esac
  done < <(git -C "$ROOT_DIR" diff --name-status --no-renames -z "$base_sha" "$remote_sha" --)
}

apply_snapshot_diff() {
  local base_sha="$1"
  local remote_sha="$2"

  git -C "$ROOT_DIR" diff --binary "$base_sha" "$remote_sha" -- | git -C "$ROOT_DIR" apply --cached --directory="$PREFIX"
  materialize_cached_snapshot_diff "$base_sha" "$remote_sha"
}

import_fast_forward_snapshot() {
  local local_split="$1"
  local remote_sha="$2"
  local method="${3:-fast_forward_snapshot_import}"

  if ! git -C "$ROOT_DIR" merge-base --is-ancestor "$local_split" "$remote_sha"; then
    echo "agent_canon_snapshot_import=diverged_history"
    die "snapshot import is unsafe because local shared-canon history diverged from '$REMOTE_NAME/$DEFAULT_BRANCH'; route the shared canon changes through an AgentCanon PR branch before running ensure-latest"
  fi

  if git -C "$ROOT_DIR" diff --quiet "$local_split" "$remote_sha" --; then
    echo "agent_canon_latest=already_current_snapshot"
    cmd_link_root 1
    return
  fi

  echo "agent_canon_update_method=$method"
  apply_snapshot_diff "$local_split" "$remote_sha"
  cmd_link_root 1
  commit_sync_paths_if_needed "$remote_sha" "$method"
}

import_snapshot_preferring_tree_match() {
  local local_split="$1"
  local local_tree="$2"
  local remote_sha="$3"
  local method="$4"
  local matched_commit=""

  if git -C "$ROOT_DIR" merge-base --is-ancestor "$local_split" "$remote_sha"; then
    import_fast_forward_snapshot "$local_split" "$remote_sha" "$method"
    return
  fi

  matched_commit="$(find_commit_by_tree "$local_tree" "$remote_sha" || true)"
  if [ -n "$matched_commit" ]; then
    echo "agent_canon_snapshot_import=tree_match_in_remote_history"
    import_fast_forward_snapshot "$matched_commit" "$remote_sha" "$method"
    return
  fi

  echo "agent_canon_snapshot_import=diverged_history"
  die "snapshot import is unsafe because local shared-canon history diverged from '$REMOTE_NAME/$DEFAULT_BRANCH' and the current prefix tree is not present in remote history; route the shared canon changes through an AgentCanon PR branch before running ensure-latest"
}

import_snapshot_from_prefix_tree() {
  local local_tree="$1"
  local remote_sha="$2"
  local method="$3"
  local local_snapshot=""

  if git -C "$ROOT_DIR" diff --quiet "$local_tree" "$remote_sha" --; then
    echo "agent_canon_latest=already_current_tree"
    cmd_link_root 1
    return
  fi

  local_snapshot="$(find_commit_by_tree "$local_tree" "$remote_sha")" || die "git subtree is unavailable and snapshot import is unsafe because the local prefix tree is not present in remote agent-canon history"
  import_fast_forward_snapshot "$local_snapshot" "$remote_sha" "$method"
}

split_prefix_or_empty() {
  git -C "$ROOT_DIR" subtree split --prefix="$PREFIX" HEAD 2>/dev/null \
    || git -C "$ROOT_DIR" subtree split --ignore-joins --prefix="$PREFIX" HEAD 2>/dev/null \
    || true
}

has_subtree_metadata() {
  git -C "$ROOT_DIR" log --format=%B --grep="git-subtree-dir: $PREFIX" --max-count=1 HEAD >/dev/null 2>&1
}

print_plan_summary() {
  local branch="$1"
  local remote_url="$2"
  local remote_source="$3"
  local remote_sha="$4"
  local remote_tree="$5"
  local local_tree="$6"
  local local_split="$7"
  local subtree_metadata="$8"
  local route="$9"
  local dirty="${10}"
  local requires_clean="${11}"
  local prefix_mode="${12:-tree}"
  local dirty_update_surface="${13:-$dirty}"

  echo "agent_canon_plan_branch=$branch"
  if [ -n "$remote_url" ]; then
    echo "agent_canon_plan_remote_url=$remote_url"
  else
    echo "agent_canon_plan_remote_url=<unset>"
  fi
  echo "agent_canon_plan_remote_source=$remote_source"
  if [ -n "$remote_sha" ]; then
    echo "agent_canon_plan_remote_sha=$remote_sha"
    echo "agent_canon_plan_remote_tree=$remote_tree"
  else
    echo "agent_canon_plan_remote_sha=<unavailable>"
    echo "agent_canon_plan_remote_tree=<unavailable>"
  fi
  echo "agent_canon_plan_local_tree=$local_tree"
  if [ -n "$local_split" ]; then
    echo "agent_canon_plan_local_split=$local_split"
  else
    echo "agent_canon_plan_local_split=unavailable"
  fi
  echo "agent_canon_plan_has_subtree_metadata=$subtree_metadata"
  echo "agent_canon_plan_prefix_mode=$prefix_mode"
  echo "agent_canon_plan_dirty_worktree=$dirty"
  echo "agent_canon_plan_dirty_update_surface=$dirty_update_surface"
  echo "agent_canon_plan_route=$route"
  echo "agent_canon_plan_requires_clean=$requires_clean"
  echo "agent_canon_plan_apply_command=bash tools/sync_agent_canon.sh ensure-latest $branch"
}

print_submodule_plan_details() {
  local parent_pin="$1"
  local worktree_head="$2"
  local worktree_status="$3"
  local remote_sha="$4"
  local deferred_ref="${5:-}"
  local deferred_branch=""
  local deferred_remote_branch=""

  echo "agent_canon_plan_submodule_local_state_checked=yes"
  echo "agent_canon_plan_submodule_parent_pin=$parent_pin"
  echo "agent_canon_plan_submodule_worktree_head=${worktree_head:-<unavailable>}"
  echo "agent_canon_plan_submodule_worktree_status=$worktree_status"
  if [ -n "$deferred_ref" ]; then
    deferred_branch="${deferred_ref%%:*}"
    deferred_remote_branch="${deferred_ref#*:}"
    echo "agent_canon_plan_submodule_deferred_branch=$deferred_branch"
    echo "agent_canon_plan_submodule_deferred_remote_branch=$deferred_remote_branch"
    echo "agent_canon_plan_submodule_deferred_remote_branch_match=yes"
  else
    echo "agent_canon_plan_submodule_deferred_branch=<none>"
    echo "agent_canon_plan_submodule_deferred_remote_branch=<none>"
    echo "agent_canon_plan_submodule_deferred_remote_branch_match=no"
  fi
  if [ -n "$remote_sha" ]; then
    if [ "$parent_pin" = "$remote_sha" ]; then
      echo "agent_canon_plan_submodule_parent_pin_remote_match=yes"
    else
      echo "agent_canon_plan_submodule_parent_pin_remote_match=no"
    fi
    if [ -n "$worktree_head" ] && [ "$worktree_head" = "$remote_sha" ]; then
      echo "agent_canon_plan_submodule_worktree_remote_match=yes"
    else
      echo "agent_canon_plan_submodule_worktree_remote_match=no"
    fi
  else
    echo "agent_canon_plan_submodule_parent_pin_remote_match=unavailable"
    echo "agent_canon_plan_submodule_worktree_remote_match=unavailable"
  fi
}

cmd_plan() {
  local branch="${1:-$DEFAULT_BRANCH}"
  local local_tree=""
  local local_split=""
  local remote_tree=""
  local remote_sha=""
  local remote_url=""
  local remote_source="unset"
  local subtree_metadata="no"
  local prefix_mode="tree"
  local route="remote_unconfigured"
  local requires_clean="no"
  local dirty="no"
  local dirty_update_surface="no"
  local submodule_worktree_head=""
  local submodule_worktree_status="not_applicable"
  local submodule_deferred_ref=""

  ensure_prefix_exists
  if is_submodule_prefix; then
    prefix_mode="submodule"
    local_tree="$(submodule_commit)"
    local_split=""
    remote_url="$(submodule_remote_url)"
    ensure_submodule_checkout
    submodule_worktree_head="$(git -C "$ROOT_DIR/$PREFIX" rev-parse HEAD 2>/dev/null || true)"
    if [ -n "$(git -C "$ROOT_DIR/$PREFIX" status --short --untracked-files=all)" ]; then
      submodule_worktree_status="dirty"
    else
      submodule_worktree_status="clean"
    fi
    if [ -n "$remote_url" ]; then
      remote_source="submodule"
    fi
  else
    local_tree="$(git -C "$ROOT_DIR" rev-parse "HEAD:$PREFIX")"
    local_split="$(split_prefix_or_empty)"
    if has_subtree_metadata; then
      subtree_metadata="yes"
    fi
  fi
  if [ -n "$(git -C "$ROOT_DIR" status --short)" ]; then
    dirty="yes"
  fi
  if [ -n "$(agent_canon_update_surface_status)" ]; then
    dirty_update_surface="yes"
  fi

  if [ -n "$PLAN_REMOTE_OVERRIDE_URL" ]; then
    remote_url="$PLAN_REMOTE_OVERRIDE_URL"
    remote_source="plan_override"
  elif [ "$prefix_mode" = "submodule" ] && [ -n "$remote_url" ]; then
    :
  elif git -C "$ROOT_DIR" remote get-url "$REMOTE_NAME" >/dev/null 2>&1; then
    remote_url="$(git -C "$ROOT_DIR" remote get-url "$REMOTE_NAME")"
    remote_source="configured"
  else
    remote_url="$(default_remote_url)"
    if [ -n "$remote_url" ]; then
      remote_source="default"
    fi
  fi

  if [ -z "$remote_url" ]; then
    print_plan_summary \
      "$branch" "$remote_url" "$remote_source" "$remote_sha" "$remote_tree" "$local_tree" \
      "$local_split" "$subtree_metadata" "$route" "$dirty" "$requires_clean" "$prefix_mode" "$dirty_update_surface"
    if [ "$prefix_mode" = "submodule" ]; then
      print_submodule_plan_details "$local_tree" "$submodule_worktree_head" "$submodule_worktree_status" "$remote_sha"
    fi
    return
  fi

  if [ "$prefix_mode" = "submodule" ]; then
    git -C "$ROOT_DIR/$PREFIX" fetch "$remote_url" "$branch"
    remote_sha="$(git -C "$ROOT_DIR/$PREFIX" rev-parse FETCH_HEAD)"
    remote_tree="$(git -C "$ROOT_DIR/$PREFIX" rev-parse "$remote_sha^{tree}")"
  else
    git -C "$ROOT_DIR" fetch "$remote_url" "$branch"
    remote_sha="$(git -C "$ROOT_DIR" rev-parse FETCH_HEAD)"
    remote_tree="$(git -C "$ROOT_DIR" rev-parse "$remote_sha^{tree}")"
  fi

  if [ "$prefix_mode" = "submodule" ]; then
    if [ "$local_tree" != "$submodule_worktree_head" ] \
      && [ "$submodule_worktree_status" = "clean" ] \
      && [ "$submodule_worktree_head" != "$remote_sha" ] \
      && git -C "$ROOT_DIR/$PREFIX" merge-base --is-ancestor "$remote_sha" "$submodule_worktree_head"; then
      submodule_deferred_ref="$(submodule_deferred_branch_pr_ref "$submodule_worktree_head" "$submodule_worktree_head" clean || true)"
      if [ -n "$submodule_deferred_ref" ]; then
        route="deferred_branch_pr"
      elif [ "$local_tree" = "$remote_sha" ]; then
        route="already_current_submodule"
      else
        route="local_contains_remote"
      fi
    elif [ "$submodule_worktree_status" = "clean" ] \
      && [ -n "$submodule_worktree_head" ] \
      && [ "$submodule_worktree_head" != "$remote_sha" ] \
      && [ "$(git -C "$ROOT_DIR/$PREFIX" rev-parse "$submodule_worktree_head^{tree}")" = "$remote_tree" ]; then
      route="local_tree_matches_remote"
    elif [ "$local_tree" = "$remote_sha" ]; then
      route="already_current_submodule"
    elif git -C "$ROOT_DIR/$PREFIX" merge-base --is-ancestor "$remote_sha" "$local_tree"; then
      submodule_deferred_ref="$(submodule_deferred_branch_pr_ref "$local_tree" "$submodule_worktree_head" "$submodule_worktree_status" || true)"
      if [ -n "$submodule_deferred_ref" ]; then
        route="deferred_branch_pr"
      else
        route="local_contains_remote"
      fi
    elif git -C "$ROOT_DIR/$PREFIX" merge-base --is-ancestor "$local_tree" "$remote_sha"; then
      route="submodule_update"
      requires_clean="yes"
    else
      route="diverged_submodule_history"
      requires_clean="yes"
    fi
  elif [ "$local_tree" = "$remote_tree" ]; then
    route="already_current_tree"
  elif [ -n "$local_split" ] && [ "$local_split" = "$remote_sha" ]; then
    route="already_current_split"
  elif [ -n "$local_split" ] && git -C "$ROOT_DIR" merge-base --is-ancestor "$remote_sha" "$local_split"; then
    route="local_contains_remote"
  elif [ -n "$local_split" ] && git -C "$ROOT_DIR" merge-base --is-ancestor "$local_split" "$remote_sha"; then
    if [ "$subtree_metadata" = "yes" ]; then
      route="subtree_pull"
    else
      route="snapshot_import_no_subtree_metadata"
    fi
    requires_clean="yes"
  elif [ -n "$local_split" ] && find_commit_by_tree "$local_tree" "$remote_sha" >/dev/null 2>&1; then
    route="snapshot_import_tree_match"
    requires_clean="yes"
  elif [ -n "$local_split" ]; then
    route="diverged_local_history"
    requires_clean="yes"
  elif find_commit_by_tree "$local_tree" "$remote_sha" >/dev/null 2>&1; then
    route="snapshot_import_no_subtree"
    requires_clean="yes"
  else
    route="snapshot_import_unsafe_tree_not_in_remote"
    requires_clean="yes"
  fi

  print_plan_summary \
    "$branch" "$remote_url" "$remote_source" "$remote_sha" "$remote_tree" "$local_tree" \
    "$local_split" "$subtree_metadata" "$route" "$dirty" "$requires_clean" "$prefix_mode" "$dirty_update_surface"
  if [ "$prefix_mode" = "submodule" ]; then
    print_submodule_plan_details "$local_tree" "$submodule_worktree_head" "$submodule_worktree_status" "$remote_sha" "$submodule_deferred_ref"
  fi
}

cmd_submodule_add() {
  local remote_url="$1"
  local branch="${2:-$DEFAULT_BRANCH}"
  require_clean_worktree
  [ -n "$remote_url" ] || die "submodule-add requires <remote-url>"
  if [ -e "$ROOT_DIR/$PREFIX" ] || git -C "$ROOT_DIR" ls-tree HEAD "$PREFIX" >/dev/null 2>&1; then
    die "prefix '$PREFIX' already exists; remove the subtree snapshot before adding a submodule"
  fi
  git -C "$ROOT_DIR" submodule add -b "$branch" "$remote_url" "$PREFIX"
  cmd_link_root 1
}

pull_or_import_snapshot() {
  local branch="$1"
  local local_split="$2"
  local remote_sha="$3"
  local local_tree="$4"
  local pull_log=""

  if ! has_subtree_metadata; then
    echo "agent_canon_subtree_pull=skipped_no_subtree_metadata"
    import_snapshot_preferring_tree_match "$local_split" "$local_tree" "$remote_sha" "snapshot_import_no_subtree_metadata"
    return
  fi

  pull_log="$(mktemp)"
  if git -C "$ROOT_DIR" subtree pull --prefix="$PREFIX" "$REMOTE_NAME" "$branch" --squash >"$pull_log" 2>&1; then
    cat "$pull_log"
    rm -f "$pull_log"
    echo "agent_canon_update_method=subtree_pull"
    cmd_link_root 1
    commit_sync_paths_if_needed "$remote_sha" "subtree_pull"
    return
  fi

  cat "$pull_log" >&2
  rm -f "$pull_log"
  echo "agent_canon_subtree_pull=failed"
  import_snapshot_preferring_tree_match "$local_split" "$local_tree" "$remote_sha" "snapshot_import_after_subtree_pull_failure"
}

cmd_add() {
  local remote_url="$1"
  local branch="${2:-$DEFAULT_BRANCH}"
  require_clean_worktree
  ensure_remote "$remote_url"
  git -C "$ROOT_DIR" fetch "$REMOTE_NAME" "$branch"
  git -C "$ROOT_DIR" subtree add --prefix="$PREFIX" "$REMOTE_NAME" "$branch" --squash
  cmd_link_root 1
}

cmd_pull() {
  local branch="${1:-$DEFAULT_BRANCH}"
  local local_split=""
  local local_tree=""
  local remote_sha=""

  if is_submodule_prefix; then
    cmd_ensure_latest "$branch"
    return
  fi

  require_clean_worktree
  ensure_existing_remote_or_default
  git -C "$ROOT_DIR" fetch "$REMOTE_NAME" "$branch"
  remote_sha="$(git -C "$ROOT_DIR" rev-parse FETCH_HEAD)"
  local_tree="$(git -C "$ROOT_DIR" rev-parse "HEAD:$PREFIX")"
  local_split="$(split_prefix_or_empty)"
  if [ -n "$local_split" ]; then
    pull_or_import_snapshot "$branch" "$local_split" "$remote_sha" "$local_tree"
    return
  fi

  echo "agent_canon_local_split=unavailable"
  import_snapshot_from_prefix_tree "$(git -C "$ROOT_DIR" rev-parse "HEAD:$PREFIX")" "$remote_sha" "snapshot_import_no_subtree"
}

cmd_ensure_latest() {
  local branch="${1:-$DEFAULT_BRANCH}"
  local local_tree=""
  local local_split=""
  local remote_tree=""
  local remote_sha=""

  ensure_prefix_exists
  if is_submodule_prefix; then
    local remote_url=""
    local local_commit=""
    local worktree_commit=""
    local submodule_status=""
    local submodule_branch=""
    local submodule_worktree_status=""
    local submodule_deferred_ref=""
    local remote_tree=""
    remote_url="$(submodule_remote_url)"
    [ -n "$remote_url" ] || die "submodule '$PREFIX' has no .gitmodules url"
    local_commit="$(submodule_commit)"
    if git -C "$ROOT_DIR/$PREFIX" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
      worktree_commit="$(git -C "$ROOT_DIR/$PREFIX" rev-parse HEAD)"
    else
      git -C "$ROOT_DIR" submodule update --init --recursive "$PREFIX"
      worktree_commit="$(git -C "$ROOT_DIR/$PREFIX" rev-parse HEAD)"
    fi
    submodule_branch="$(git -C "$ROOT_DIR/$PREFIX" branch --show-current || true)"
    if [ -n "$(git -C "$ROOT_DIR/$PREFIX" status --short --untracked-files=all)" ]; then
      submodule_worktree_status="dirty"
    else
      submodule_worktree_status="clean"
    fi
    echo "agent_canon_latest_submodule_local_state_checked=yes"
    echo "agent_canon_latest_submodule_local_state_source=$PREFIX"
    echo "agent_canon_latest_submodule_branch=${submodule_branch:-detached}"
    echo "agent_canon_latest_submodule_worktree_status=$submodule_worktree_status"
    git -C "$ROOT_DIR/$PREFIX" fetch "$remote_url" "$branch"
    remote_sha="$(git -C "$ROOT_DIR/$PREFIX" rev-parse FETCH_HEAD)"
    remote_tree="$(git -C "$ROOT_DIR/$PREFIX" rev-parse "$remote_sha^{tree}")"
    echo "agent_canon_local_submodule=$local_commit"
    echo "agent_canon_worktree_submodule=$worktree_commit"
    echo "agent_canon_remote=$remote_sha"
    if [ "$worktree_commit" != "$local_commit" ]; then
      submodule_status="$(git -C "$ROOT_DIR/$PREFIX" status --short)"
      if [ -z "$submodule_status" ] && [ -n "$submodule_branch" ] && [ "$worktree_commit" != "$remote_sha" ] && git -C "$ROOT_DIR/$PREFIX" merge-base --is-ancestor "$remote_sha" "$worktree_commit"; then
        submodule_deferred_ref="$(submodule_deferred_branch_pr_ref "$worktree_commit" "$worktree_commit" clean || true)"
        if [ -n "$submodule_deferred_ref" ]; then
          echo "agent_canon_latest=deferred_branch_pr"
          echo "agent_canon_latest_branch=${submodule_deferred_ref%%:*}"
          echo "agent_canon_latest_remote_branch=${submodule_deferred_ref#*:}"
          echo "agent_canon_latest_remote_branch_match=yes"
          echo "agent_canon_latest_parent_pin_status=stale"
          echo "agent_canon_latest_next=after_agentcanon_PR_merge_rerun_make_agent-canon-ensure-latest"
          cmd_link_root
          return
        fi
      fi
      if [ "$worktree_commit" = "$remote_sha" ] && [ -z "$submodule_status" ]; then
        echo "agent_canon_latest=parent_pin_pending"
        cmd_link_root 1
        commit_sync_paths_if_needed "$remote_sha" "submodule_parent_pin"
        return
      fi
      if [ -z "$submodule_status" ] \
        && [ "$(git -C "$ROOT_DIR/$PREFIX" rev-parse "$worktree_commit^{tree}")" = "$remote_tree" ]; then
        echo "agent_canon_latest=local_tree_matches_remote"
        if [ "$worktree_commit" != "$remote_sha" ]; then
          git -C "$ROOT_DIR/$PREFIX" checkout "$remote_sha"
        fi
        cmd_link_root
        commit_sync_paths_if_needed "$remote_sha" "submodule_update"
        return
      fi
      echo "agent_canon_latest=local_submodule_worktree_differs_from_parent_pin"
      die "submodule '$PREFIX' worktree HEAD differs from parent gitlink; commit the parent pin or route the AgentCanon branch through a PR before ensure-latest"
    fi
    if [ "$local_commit" = "$remote_sha" ]; then
      echo "agent_canon_latest=already_current_submodule"
      cmd_link_root
      return
    fi
    if [ "$worktree_commit" = "$local_commit" ] \
      && [ "$submodule_worktree_status" = "clean" ] \
      && [ "$(git -C "$ROOT_DIR/$PREFIX" rev-parse "$local_commit^{tree}")" = "$remote_tree" ]; then
      echo "agent_canon_latest=local_tree_matches_remote"
      if [ "$worktree_commit" != "$remote_sha" ]; then
        git -C "$ROOT_DIR/$PREFIX" checkout "$remote_sha"
      fi
      cmd_link_root
      commit_sync_paths_if_needed "$remote_sha" "submodule_update"
      return
    fi
    if git -C "$ROOT_DIR/$PREFIX" merge-base --is-ancestor "$remote_sha" "$local_commit"; then
      submodule_status="$(git -C "$ROOT_DIR/$PREFIX" status --short --untracked-files=all)"
      submodule_deferred_ref="$(submodule_deferred_branch_pr_ref "$local_commit" "$worktree_commit" "$([ -z "$submodule_status" ] && echo clean || echo dirty)" || true)"
      if [ -n "$submodule_deferred_ref" ]; then
        echo "agent_canon_latest=deferred_branch_pr"
        echo "agent_canon_latest_branch=${submodule_deferred_ref%%:*}"
        echo "agent_canon_latest_remote_branch=${submodule_deferred_ref#*:}"
        echo "agent_canon_latest_remote_branch_match=yes"
        echo "agent_canon_latest_next=after_agentcanon_PR_merge_rerun_make_agent-canon-ensure-latest"
        cmd_link_root
        return
      fi
      echo "agent_canon_latest=local_contains_remote"
      echo "agent_canon_latest_next=push_agentcanon_branch_open_agent-canon_PR_then_rerun_ensure-latest"
      die "submodule '$PREFIX' parent pin contains commits not in remote main; push an AgentCanon branch and open a PR before treating it as latest"
    fi
    submodule_status="$(git -C "$ROOT_DIR/$PREFIX" status --short)"
    if [ "$worktree_commit" != "$remote_sha" ] && [ -n "$submodule_status" ]; then
      die "submodule '$PREFIX' is dirty; commit or clean it before updating"
    fi
    ensure_surface_sync_safe
    echo "agent_canon_latest=updating_submodule"
    if [ "$worktree_commit" != "$remote_sha" ]; then
      git -C "$ROOT_DIR/$PREFIX" checkout "$remote_sha"
    fi
    cmd_link_root
    commit_sync_paths_if_needed "$remote_sha" "submodule_update"
    return
  fi

  ensure_existing_remote_or_default
  git -C "$ROOT_DIR" fetch "$REMOTE_NAME" "$branch"
  remote_sha="$(git -C "$ROOT_DIR" rev-parse FETCH_HEAD)"
  remote_tree="$(git -C "$ROOT_DIR" rev-parse "$remote_sha^{tree}")"
  local_tree="$(git -C "$ROOT_DIR" rev-parse "HEAD:$PREFIX")"
  local_split="$(split_prefix_or_empty)"

  if [ -n "$local_split" ]; then
    echo "agent_canon_local_split=$local_split"
  else
    echo "agent_canon_local_split=unavailable"
  fi
  echo "agent_canon_remote=$remote_sha"

  if [ "$local_tree" = "$remote_tree" ]; then
    echo "agent_canon_latest=already_current_tree"
    if [ -n "$(git -C "$ROOT_DIR" status --short)" ]; then
      cmd_check
    else
      cmd_link_root 1
    fi
    return
  fi

  if [ -n "$local_split" ] && [ "$local_split" = "$remote_sha" ]; then
    echo "agent_canon_latest=already_current"
    if [ -n "$(git -C "$ROOT_DIR" status --short)" ]; then
      cmd_check
    else
      cmd_link_root 1
    fi
    return
  fi

  if [ -n "$local_split" ] && git -C "$ROOT_DIR" merge-base --is-ancestor "$remote_sha" "$local_split"; then
    echo "agent_canon_latest=local_contains_remote"
    if [ -n "$(git -C "$ROOT_DIR" status --short)" ]; then
      cmd_check
    else
      cmd_link_root 1
    fi
    return
  fi

  require_clean_worktree
  echo "agent_canon_latest=pulling_remote"
  if [ -n "$local_split" ]; then
    pull_or_import_snapshot "$branch" "$local_split" "$remote_sha" "$local_tree"
  else
    import_snapshot_from_prefix_tree "$local_tree" "$remote_sha" "snapshot_import_no_subtree"
  fi
}

cmd_push() {
  local branch="${1:-$DEFAULT_BRANCH}"
  local local_split=""
  [ -d "$ROOT_DIR/$PREFIX" ] || die "prefix '$PREFIX' does not exist"
  if is_submodule_prefix; then
    local submodule_status=""
    local remote_url=""
    remote_url="$(submodule_remote_url)"
    [ -n "$remote_url" ] || die "submodule '$PREFIX' has no .gitmodules url"
    if [ "$branch" = "$DEFAULT_BRANCH" ] && [ "${AGENT_CANON_ALLOW_DIRECT_MAIN_PUSH:-0}" != "1" ]; then
      die "submodule push to '$DEFAULT_BRANCH' is forbidden; push a normal AgentCanon PR branch or set AGENT_CANON_ALLOW_DIRECT_MAIN_PUSH=1 intentionally"
    fi
    submodule_status="$(git -C "$ROOT_DIR/$PREFIX" status --short)"
    [ -z "$submodule_status" ] || die "submodule '$PREFIX' is dirty; commit or clean it before pushing"
    git -C "$ROOT_DIR/$PREFIX" rev-parse --verify HEAD^{commit} >/dev/null 2>&1 \
      || die "submodule '$PREFIX' has no valid HEAD"
    git -C "$ROOT_DIR/$PREFIX" push "$remote_url" "HEAD:refs/heads/${branch}"
    return
  fi
  require_existing_remote
  require_clean_worktree
  local_split="$(split_prefix_or_empty)"
  [ -n "$local_split" ] || die "could not split prefix '$PREFIX'"
  git -C "$ROOT_DIR" push "$REMOTE_NAME" "${local_split}:refs/heads/${branch}"
}

cmd_status() {
  local remote_url=""
  local spec=""
  if git -C "$ROOT_DIR" remote get-url "$REMOTE_NAME" >/dev/null 2>&1; then
    remote_url="$(git -C "$ROOT_DIR" remote get-url "$REMOTE_NAME")"
  fi
  echo "repo_root=$ROOT_DIR"
  echo "prefix=$PREFIX"
  echo "remote_name=$REMOTE_NAME"
  echo "default_branch=$DEFAULT_BRANCH"
  local mode=""
  mode="$(prefix_git_mode)"
  echo "prefix_mode=$mode"
  if [ "$mode" = "160000" ]; then
    echo "prefix_mode_name=submodule"
    echo "submodule_url=$(submodule_remote_url)"
    echo "submodule_pin=$(submodule_commit)"
  elif [ "$mode" = "040000" ]; then
    echo "prefix_mode_name=legacy_tree"
  else
    echo "prefix_mode_name=unknown"
  fi
  if [ -n "$remote_url" ]; then
    echo "remote_url=$remote_url"
  else
    echo "remote_url=<unset>"
  fi
  if [ -d "$ROOT_DIR/$PREFIX" ]; then
    echo "prefix_status=present"
  else
    echo "prefix_status=missing"
  fi
  while IFS= read -r spec; do
    local path="${spec%%:*}"
    local target="${spec#*:}"
    local abs_path="$ROOT_DIR/$path"
    if [ -L "$abs_path" ] && [ "$(readlink "$abs_path")" = "$target" ]; then
      echo "link[$path]=ok"
    elif [ -e "$abs_path" ]; then
      echo "link[$path]=drift"
    else
      echo "link[$path]=missing"
    fi
  done < <(build_link_specs)

  while IFS= read -r spec; do
    local path="${spec%%:*}"
    local source="${spec#*:}"
    local abs_path="$ROOT_DIR/$path"
    local abs_source="$ROOT_DIR/$source"
    if [ -f "$abs_path" ] && [ -f "$abs_source" ] && cmp -s "$abs_path" "$abs_source"; then
      echo "copy[$path]=ok"
    elif [ -e "$abs_path" ]; then
      echo "copy[$path]=drift"
    else
      echo "copy[$path]=missing"
    fi
  done < <(build_copy_specs)

  while IFS= read -r spec; do
    local path="${spec%%:*}"
    local abs_path="$ROOT_DIR/$path"
    if [ -e "$abs_path" ] && [ ! -L "$abs_path" ]; then
      echo "regular[$path]=ok"
    elif [ -L "$abs_path" ]; then
      echo "regular[$path]=symlink"
    else
      echo "regular[$path]=missing"
    fi
  done < <(build_regular_specs)

  while IFS= read -r path; do
    [ -n "$path" ] || continue
    local abs_path="$ROOT_DIR/$path"
    if [ -e "$abs_path" ] || [ -L "$abs_path" ]; then
      echo "absent[$path]=present"
    else
      echo "absent[$path]=ok"
    fi
  done < <(build_root_absent_paths)
}

main() {
  require_git_repo
  cd "$ROOT_DIR"

  local subcommand="${1:-}"
  case "$subcommand" in
    link-root)
      cmd_link_root
      ;;
    plan)
      cmd_plan "${2:-$DEFAULT_BRANCH}"
      ;;
    check)
      cmd_check
      ;;
    snapshot)
      cmd_snapshot
      ;;
    add)
      [ "${2:-}" ] || die "add requires <remote-url>"
      cmd_add "$2" "${3:-$DEFAULT_BRANCH}"
      ;;
    submodule-add)
      [ "${2:-}" ] || die "submodule-add requires <remote-url>"
      cmd_submodule_add "$2" "${3:-$DEFAULT_BRANCH}"
      ;;
    pull)
      cmd_pull "${2:-$DEFAULT_BRANCH}"
      ;;
    ensure-latest)
      cmd_ensure_latest "${2:-$DEFAULT_BRANCH}"
      ;;
    push)
      cmd_push "${2:-$DEFAULT_BRANCH}"
      ;;
    status)
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
