#!/usr/bin/env bash
# @dependency-start
# responsibility Provides sync agent canon repository automation.
# upstream implementation ./agent_tools/check_dependency_headers.py validates dependency manifests
# upstream implementation ../tests/agent_tools/test_check_dependency_headers.py tests dependency manifest checker
# downstream implementation ../documents/codex-configuration-reference.md root symlink view for Codex config docs
# downstream implementation ../documents/codex-configuration-slides.md root symlink view for Codex config slides
# downstream implementation ../documents/project-template-overview-slides.md root symlink view for template overview slides
# downstream implementation ../documents/algorithm-implementation-boundary.md root symlink view for algorithm boundary policy
# downstream implementation ../documents/object-oriented-design.md root symlink view for OOP policy
# downstream implementation ../documents/result-log-retention-and-visualization.md root symlink view
# downstream implementation ../documents/repo-local-tool-imports.md root symlink view
# downstream implementation ../documents/tools/tool-docs.toml root symlink view
# downstream implementation ../documents/tools/oop/python/readability.md root symlink view
# downstream implementation ../documents/tools/oop/python/rule_inventory.md root symlink view
# downstream implementation ../documents/tools/oop/cpp/readability.md root symlink view
# downstream implementation ../documents/tools/oop/cpp/rule_inventory.md root symlink view
# downstream implementation ../documents/agent-canon-github-remote.md root symlink view
# downstream implementation ../documents/github-copilot-configuration.md root symlink view
# downstream implementation ../documents/template-github-remote.md root symlink view
# downstream implementation ../tests/agent_tools/test_dependency_manifest_tools.py root symlink view for manifest tests
# downstream implementation ../tests/agent_tools/test_compare_agent_run_paths.py root symlink view for run path comparison tests
# downstream implementation ../tests/agent_tools/test_evaluate_agent_run.py root symlink view for eval tests
# downstream implementation ../tests/agent_tools/test_evaluate_skill_workflow_prompts.py root symlink view for prompt eval tests
# downstream implementation ../tests/agent_tools/test_goal_loop.py root symlink view for goal loop tests
# downstream implementation ../tests/agent_tools/test_check_static_any.py root symlink view for explicit Any tests
# downstream implementation ../tests/agent_tools/test_repo_mcp_server.py root symlink view for MCP tests
# downstream implementation ../tests/agent_tools/test_check_algorithm_module_nested_contract.py root symlink view
# downstream implementation ../tests/agent_tools/test_check_log_helper_names.py root symlink view
# downstream implementation ../tests/agent_tools/test_tool_catalog.py root symlink view
# downstream implementation ../tests/agent_tools/test_tool_drift.py root symlink view
# downstream implementation ../tests/agent_tools/test_oop_rule_inventory.py root symlink view
# downstream implementation ../tests/agent_tools/test_compare_codex_token_footprints.py root symlink view
# downstream implementation ../tests/tools/test_container_config.py root symlink view
# downstream implementation ../tests/tools/test_result_log_tools.py root symlink view
# downstream implementation ../tests/tools/test_update_latest_result.py root symlink view
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
  # Normal submodule-era routes
  bash tools/sync_agent_canon.sh plan [branch]
  bash tools/sync_agent_canon.sh submodule-review [branch]
  bash tools/sync_agent_canon.sh align-main [branch]
  bash tools/sync_agent_canon.sh link-root
  bash tools/sync_agent_canon.sh check
  bash tools/sync_agent_canon.sh submodule-add <remote-url> [branch]
  bash tools/sync_agent_canon.sh ensure-latest [branch]
  bash tools/sync_agent_canon.sh status

  # Legacy / low-level compatibility routes
  bash tools/sync_agent_canon.sh snapshot
  bash tools/sync_agent_canon.sh add <remote-url> [branch]
  bash tools/sync_agent_canon.sh pull [branch]
  bash tools/sync_agent_canon.sh push <proposal-branch>

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
    die "worktree is dirty; commit or stash changes before AgentCanon operations"
  fi
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
  done < <(build_removed_legacy_paths)

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
  if copy_source_is_optional_missing "$path" "$source"; then
    rm -rf "$abs_path"
    return 0
  fi
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

copy_source_is_optional_missing() {
  local path="$1"
  local source="$2"
  [ "$path" = ".github/scripts/checkout_agent_canon_submodule.sh" ] \
    && [ ! -e "$ROOT_DIR/$source" ]
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
  while IFS= read -r path; do
    [ -n "$path" ] || continue
    paths+=("$path")
  done < <(build_removed_legacy_paths)

  [ "${#paths[@]}" -gt 0 ] || return
  status="$(git -C "$ROOT_DIR" status --short -- "${paths[@]}")"
  if [ -n "$status" ]; then
    echo "$status" >&2
    die "shared surface has uncommitted changes; commit or stash them first, or rerun with AGENT_CANON_FORCE_RELINK=1"
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
  done < <(build_removed_legacy_paths)

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
    if copy_source_is_optional_missing "$path" "$source"; then
      [ ! -e "$abs_path" ] || echo "copy[$path]=drift" >&2
      [ ! -e "$abs_path" ] || failed=1
      continue
    fi
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
      echo "legacy[$path]=present" >&2
      failed=1
    fi
  done < <(build_removed_legacy_paths)

  if goal_is_shared_symlink; then
    echo "goal.md=shared-symlink" >&2
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
    if [[ "$spec" == .github/scripts/checkout_agent_canon_submodule.sh:* ]] \
      && [ ! -e "$ROOT_DIR/${spec#*:}" ]; then
      continue
    fi
    git -C "$ROOT_DIR" add -A -- "${spec%%:*}"
  done < <(
    {
      build_link_specs
      build_copy_specs
    }
  )
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
    die "snapshot import is unsafe because local shared-canon history diverged from '$REMOTE_NAME/$DEFAULT_BRANCH'; update the proposal branch or merge the shared canon changes before running ensure-latest"
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
  die "snapshot import is unsafe because local shared-canon history diverged from '$REMOTE_NAME/$DEFAULT_BRANCH' and the current prefix tree is not present in remote history; update the proposal branch or merge the shared canon changes before running ensure-latest"
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

  echo "agent_canon_plan_submodule_parent_pin=$parent_pin"
  echo "agent_canon_plan_submodule_worktree_head=${worktree_head:-<unavailable>}"
  echo "agent_canon_plan_submodule_worktree_status=$worktree_status"
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
    if [ "$local_tree" = "$remote_sha" ]; then
      route="already_current_submodule"
    elif git -C "$ROOT_DIR/$PREFIX" merge-base --is-ancestor "$remote_sha" "$local_tree"; then
      route="local_contains_remote"
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
    print_submodule_plan_details "$local_tree" "$submodule_worktree_head" "$submodule_worktree_status" "$remote_sha"
  fi
}

cmd_submodule_review() {
  local branch="${1:-$DEFAULT_BRANCH}"
  local remote_url=""
  local parent_pin=""
  local worktree_head=""
  local remote_sha=""
  local status=""
  local history_status=""
  local merge_conflicts="not_checked"
  local proposal_required="no"
  local align_allowed="no"
  local cherry_equivalent="not_checked"
  local tree_match_commit=""
  local next_action="none"

  ensure_prefix_exists
  is_submodule_prefix || die "submodule-review requires '$PREFIX' to be a git submodule"
  remote_url="$(submodule_remote_url)"
  [ -n "$remote_url" ] || die "submodule '$PREFIX' has no .gitmodules url"

  ensure_submodule_checkout
  git -C "$ROOT_DIR/$PREFIX" fetch "$remote_url" "$branch" >/dev/null
  parent_pin="$(submodule_commit)"
  worktree_head="$(git -C "$ROOT_DIR/$PREFIX" rev-parse HEAD)"
  remote_sha="$(git -C "$ROOT_DIR/$PREFIX" rev-parse FETCH_HEAD)"
  status="$(git -C "$ROOT_DIR/$PREFIX" status --short)"

  echo "agent_canon_submodule_review_prefix=$PREFIX"
  echo "agent_canon_submodule_review_branch=$branch"
  echo "agent_canon_submodule_review_remote_url=$remote_url"
  echo "agent_canon_submodule_parent_pin=$parent_pin"
  echo "agent_canon_submodule_worktree_head=$worktree_head"
  echo "agent_canon_submodule_remote_sha=$remote_sha"

  if [ -n "$status" ]; then
    echo "agent_canon_submodule_worktree_status=dirty"
    echo "agent_canon_submodule_history_status=dirty_worktree"
    echo "agent_canon_submodule_merge_conflicts=not_checked"
    echo "agent_canon_submodule_proposal_required=yes_after_commit"
    echo "agent_canon_submodule_align_main_allowed=no"
    echo "agent_canon_submodule_next=commit_submodule_changes_then_run_push_proposal"
    return
  fi
  echo "agent_canon_submodule_worktree_status=clean"

  if [ "$worktree_head" = "$remote_sha" ]; then
    history_status="already_current"
    next_action="none"
    align_allowed="yes"
  elif git -C "$ROOT_DIR/$PREFIX" merge-base --is-ancestor "$worktree_head" "$remote_sha"; then
    history_status="behind_remote"
    merge_conflicts="no"
    next_action="run_apply"
    align_allowed="yes"
  elif git -C "$ROOT_DIR/$PREFIX" merge-base --is-ancestor "$remote_sha" "$worktree_head"; then
    history_status="ahead_of_remote"
    merge_conflicts="no"
    proposal_required="yes"
    next_action="push_proposal"
  else
    merge_conflicts="$(submodule_merge_conflicts "$worktree_head" "$remote_sha")"
    cherry_equivalent="$(submodule_cherry_equivalent_to_remote "$remote_sha" "$worktree_head")"
    tree_match_commit="$(find_submodule_commit_by_tree "$(git -C "$ROOT_DIR/$PREFIX" rev-parse "$worktree_head^{tree}")" "$remote_sha" || true)"
    if [ "$cherry_equivalent" = "yes" ] || [ -n "$tree_match_commit" ]; then
      history_status="local_changes_already_in_remote"
      align_allowed="yes"
      next_action="align_main"
    elif [ "$merge_conflicts" = "no" ]; then
      history_status="diverged_clean_merge"
      proposal_required="yes"
      next_action="merge_remote_then_push_proposal"
    else
      history_status="diverged_conflict"
      proposal_required="yes"
      next_action="resolve_conflicts_in_agentcanon_pr"
    fi
  fi

  if [ "$cherry_equivalent" = "not_checked" ] && [ "$align_allowed" != "yes" ]; then
    cherry_equivalent="$(submodule_cherry_equivalent_to_remote "$remote_sha" "$worktree_head")"
  fi

  echo "agent_canon_submodule_history_status=$history_status"
  echo "agent_canon_submodule_merge_conflicts=$merge_conflicts"
  echo "agent_canon_submodule_cherry_equivalent_in_remote=$cherry_equivalent"
  if [ -n "$tree_match_commit" ]; then
    echo "agent_canon_submodule_tree_match_commit=$tree_match_commit"
  else
    echo "agent_canon_submodule_tree_match_commit=<unset>"
  fi
  echo "agent_canon_submodule_proposal_required=$proposal_required"
  echo "agent_canon_submodule_align_main_allowed=$align_allowed"
  echo "agent_canon_submodule_next=$next_action"
  echo "agent_canon_submodule_apply_command=bash tools/update_agent_canon.sh apply $branch"
  echo "agent_canon_submodule_proposal_command=bash tools/update_agent_canon.sh push-proposal"
  echo "agent_canon_submodule_align_command=bash tools/update_agent_canon.sh align-main $branch"
}

cmd_align_main() {
  local branch="${1:-$DEFAULT_BRANCH}"
  local remote_url=""
  local parent_pin=""
  local worktree_head=""
  local remote_sha=""
  local status=""
  local cherry_equivalent=""
  local tree_match_commit=""

  ensure_prefix_exists
  is_submodule_prefix || die "align-main requires '$PREFIX' to be a git submodule"
  remote_url="$(submodule_remote_url)"
  [ -n "$remote_url" ] || die "submodule '$PREFIX' has no .gitmodules url"

  ensure_submodule_checkout
  git -C "$ROOT_DIR/$PREFIX" fetch "$remote_url" "$branch" >/dev/null
  parent_pin="$(submodule_commit)"
  worktree_head="$(git -C "$ROOT_DIR/$PREFIX" rev-parse HEAD)"
  remote_sha="$(git -C "$ROOT_DIR/$PREFIX" rev-parse FETCH_HEAD)"
  status="$(git -C "$ROOT_DIR/$PREFIX" status --short)"
  [ -z "$status" ] || die "submodule '$PREFIX' is dirty; commit or clean it before aligning to main"

  if [ "$worktree_head" = "$remote_sha" ]; then
    echo "agent_canon_align_main_allowed=yes"
    echo "agent_canon_submodule_parent_pin=$parent_pin"
    echo "agent_canon_submodule_worktree_head=$worktree_head"
    echo "agent_canon_submodule_remote_sha=$remote_sha"
    cmd_link_root 1
    if [ "$parent_pin" != "$remote_sha" ]; then
      commit_sync_paths_if_needed "$remote_sha" "submodule_align_main"
      echo "agent_canon_align_main=updated_to_remote"
      return
    fi
    echo "agent_canon_align_main=already_current"
    return
  fi

  tree_match_commit="$(find_submodule_commit_by_tree "$(git -C "$ROOT_DIR/$PREFIX" rev-parse "$worktree_head^{tree}")" "$remote_sha" || true)"
  cherry_equivalent="$(submodule_cherry_equivalent_to_remote "$remote_sha" "$worktree_head")"

  if ! git -C "$ROOT_DIR/$PREFIX" merge-base --is-ancestor "$worktree_head" "$remote_sha" \
    && [ -z "$tree_match_commit" ] \
    && [ "$cherry_equivalent" != "yes" ]; then
    echo "agent_canon_align_main_allowed=no"
    echo "agent_canon_submodule_parent_pin=$parent_pin"
    echo "agent_canon_submodule_worktree_head=$worktree_head"
    echo "agent_canon_submodule_remote_sha=$remote_sha"
    die "local submodule commits are not known to be included in remote main; push a proposal PR or merge remote first"
  fi

  echo "agent_canon_align_main_allowed=yes"
  echo "agent_canon_submodule_parent_pin=$parent_pin"
  echo "agent_canon_submodule_worktree_head=$worktree_head"
  echo "agent_canon_submodule_remote_sha=$remote_sha"
  git -C "$ROOT_DIR/$PREFIX" checkout "$remote_sha" >/dev/null
  cmd_link_root 1
  commit_sync_paths_if_needed "$remote_sha" "submodule_align_main"
  echo "agent_canon_align_main=updated_to_remote"
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
    remote_url="$(submodule_remote_url)"
    [ -n "$remote_url" ] || die "submodule '$PREFIX' has no .gitmodules url"
    local_commit="$(submodule_commit)"
    if git -C "$ROOT_DIR/$PREFIX" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
      worktree_commit="$(git -C "$ROOT_DIR/$PREFIX" rev-parse HEAD)"
      if [ "$worktree_commit" != "$local_commit" ]; then
        echo "agent_canon_local_submodule=$local_commit"
        echo "agent_canon_worktree_submodule=$worktree_commit"
        echo "agent_canon_latest=local_submodule_worktree_differs_from_parent_pin"
        die "submodule '$PREFIX' worktree HEAD differs from parent gitlink; commit the parent pin, align main, or push a proposal before ensure-latest"
      fi
    else
      git -C "$ROOT_DIR" submodule update --init --recursive "$PREFIX"
      worktree_commit="$(git -C "$ROOT_DIR/$PREFIX" rev-parse HEAD)"
    fi
    git -C "$ROOT_DIR/$PREFIX" fetch "$remote_url" "$branch"
    remote_sha="$(git -C "$ROOT_DIR/$PREFIX" rev-parse FETCH_HEAD)"
    echo "agent_canon_local_submodule=$local_commit"
    echo "agent_canon_worktree_submodule=$worktree_commit"
    echo "agent_canon_remote=$remote_sha"
    if [ "$local_commit" = "$remote_sha" ]; then
      echo "agent_canon_latest=already_current_submodule"
      cmd_link_root
      return
    fi
    if git -C "$ROOT_DIR/$PREFIX" merge-base --is-ancestor "$remote_sha" "$local_commit"; then
      echo "agent_canon_latest=local_contains_remote"
      echo "agent_canon_latest_next=push_proposal_or_open_agent-canon_PR_then_rerun_ensure-latest"
      die "submodule '$PREFIX' parent pin contains commits not in remote main; push a proposal or open an AgentCanon PR before treating it as latest"
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
      die "submodule push to '$DEFAULT_BRANCH' is forbidden; use 'bash tools/update_agent_canon.sh push-proposal <branch>' or set AGENT_CANON_ALLOW_DIRECT_MAIN_PUSH=1 intentionally"
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
    if copy_source_is_optional_missing "$path" "$source"; then
      if [ -e "$abs_path" ]; then
        echo "copy[$path]=drift"
      else
        echo "copy[$path]=skipped"
      fi
      continue
    fi
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
    submodule-review)
      cmd_submodule_review "${2:-$DEFAULT_BRANCH}"
      ;;
    align-main)
      cmd_align_main "${2:-$DEFAULT_BRANCH}"
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
