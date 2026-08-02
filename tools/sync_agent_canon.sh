#!/usr/bin/env bash
# @dependency-start
# contract tool
# responsibility Provides sync agent canon repository automation.
# upstream design ../documents/runtime/SHARED_RUNTIME_SURFACES.md shared surface ownership policy
# upstream design ../documents/runtime/shared-runtime-surfaces.toml machine-readable surface manifest
# upstream implementation ./agent_tools/surface_manifest.py renders link, copy, regular, and root-absent specs
# downstream implementation ../tests/tools/test_update_agent_canon.py verifies sync/update behavior
# @dependency-end
set -euo pipefail
export GIT_TERMINAL_PROMPT="${GIT_TERMINAL_PROMPT:-0}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
source "${SCRIPT_DIR}/lib/git_authority.sh"
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
SURFACE_MANIFEST="${AGENT_CANON_SURFACE_MANIFEST:-documents/runtime/shared-runtime-surfaces.toml}"
PROTECTED_GIT_NEXT_ACTION="request_explicit_user_approval_then_rerun_same_command_with_inline_git_authority_and_reason"
COMMIT_AUTOMATION_AUTHOR_NAME="AgentCanon Sync Automation"
COMMIT_AUTOMATION_AUTHOR_EMAIL="agent-canon-sync@automation.invalid"
COMMIT_PROVENANCE_NEXT_ACTION="set AGENT_CANON_COMMIT_REQUEST_EVIDENCE=evidence:<64 lowercase hex> and rerun the same command"

usage() {
  cat <<EOF
Usage:
  bash tools/sync_agent_canon.sh plan [branch]
  AGENT_CANON_COMMIT_REQUEST_EVIDENCE=evidence:<sha256-of-exact-authorization-evidence-bytes> bash tools/sync_agent_canon.sh link-root
  bash tools/sync_agent_canon.sh check
  AGENT_CANON_COMMIT_REQUEST_EVIDENCE=evidence:<sha256-of-exact-authorization-evidence-bytes> bash tools/sync_agent_canon.sh submodule-add <remote-url> [branch]
  AGENT_CANON_COMMIT_REQUEST_EVIDENCE=evidence:<sha256-of-exact-authorization-evidence-bytes> bash tools/sync_agent_canon.sh ensure-latest [branch]
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

require_protected_git_authority() {
  local mode="$1"
  if git_authority_check_protected_git_authority "$mode"; then
    return 0
  fi

  echo "DESTRUCTIVE_GIT_GUARD=block"
  echo "BRANCH_WORKTREE_CREATION_GUARD=block"
  echo "AGENT_CANON_PROTECTED_GIT_SUBCOMMAND=$mode"
  echo "NEXT_ACTION=$PROTECTED_GIT_NEXT_ACTION"
  die "protected AgentCanon update requires inherited branch/worktree and explicit destructive approval authority"
}

require_commit_request_evidence() {
  local mode="$1"
  if git_authority_check_commit_request_evidence; then
    return 0
  fi

  echo "COMMIT_PROVENANCE_GUARD=block"
  echo "AGENT_CANON_COMMIT_PROVENANCE_SUBCOMMAND=$mode"
  echo "NEXT_ACTION=$COMMIT_PROVENANCE_NEXT_ACTION"
  die "auto-commit requires AGENT_CANON_COMMIT_REQUEST_EVIDENCE=evidence:<64 lowercase hex>"
}

require_commit_provenance() {
  local mode="$1"
  if git_authority_check_commit_provenance "$mode"; then
    return 0
  fi

  if ! git_authority_check_protected_git_authority "$mode"; then
    echo "DESTRUCTIVE_GIT_GUARD=block"
    echo "BRANCH_WORKTREE_CREATION_GUARD=block"
    echo "AGENT_CANON_PROTECTED_GIT_SUBCOMMAND=$mode"
    echo "NEXT_ACTION=$PROTECTED_GIT_NEXT_ACTION"
    die "protected AgentCanon update requires inherited branch/worktree and explicit destructive approval authority"
  fi

  echo "COMMIT_PROVENANCE_GUARD=block"
  echo "AGENT_CANON_COMMIT_PROVENANCE_SUBCOMMAND=$mode"
  echo "NEXT_ACTION=$COMMIT_PROVENANCE_NEXT_ACTION"
  die "auto-commit requires AGENT_CANON_COMMIT_REQUEST_EVIDENCE=evidence:<64 lowercase hex>"
}

resolve_remote_branch_sha() {
  local remote="$1"
  local branch="$2"
  local expected_ref="refs/heads/$branch"
  local output=""
  local candidate_sha=""
  local candidate_ref=""
  local resolved_sha=""
  local match_count=0

  output="$(git ls-remote --exit-code "$remote" "$expected_ref")" \
    || die "remote branch '$remote#$branch' is missing or unreachable"
  while read -r candidate_sha candidate_ref; do
    [ "$candidate_ref" = "$expected_ref" ] || continue
    resolved_sha="$candidate_sha"
    match_count=$((match_count + 1))
  done <<<"$output"
  [ "$match_count" -eq 1 ] \
    || die "remote branch '$remote#$branch' resolved ambiguously ($match_count matches)"
  [[ "$resolved_sha" =~ ^[0-9a-fA-F]{40}([0-9a-fA-F]{24})?$ ]] \
    || die "remote branch '$remote#$branch' returned invalid object id '$resolved_sha'"
  printf '%s\n' "$resolved_sha"
}

ensure_remote_commit_object() {
  local repo="$1"
  local remote="$2"
  local sha="$3"
  local resolved=""

  if ! git -C "$repo" cat-file -e "$sha^{commit}" 2>/dev/null; then
    git -C "$repo" fetch --no-write-fetch-head "$remote" "$sha" >/dev/null
  fi
  resolved="$(git -C "$repo" rev-parse --verify "$sha^{commit}" 2>/dev/null || true)"
  [ "$resolved" = "$sha" ] \
    || die "remote object '$sha' is not an available commit in '$repo'"
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

prefix_index_mode() {
  git -C "$ROOT_DIR" ls-files --stage -- "$PREFIX" 2>/dev/null \
    | awk -v prefix="$PREFIX" '$3 == "0" && $4 == prefix { print $1; exit }'
}

is_submodule_prefix() {
  [ "$(prefix_git_mode)" = "160000" ] \
    || [ "$(prefix_index_mode)" = "160000" ]
}

submodule_checkout_initialized() {
  [ -e "$ROOT_DIR/$PREFIX/.git" ] \
    && git -C "$ROOT_DIR/$PREFIX" rev-parse --is-inside-work-tree >/dev/null 2>&1
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

submodule_remote_branch_for_head() {
  local commit="$1"
  local remote_ref=""
  local remote_branch=""
  local remote_sha=""

  [ -n "$commit" ] || return 1

  while IFS= read -r remote_ref; do
    [ -n "$remote_ref" ] || continue
    case "$remote_ref" in
      */HEAD)
        continue
        ;;
    esac
    remote_branch="${remote_ref#*/}"
    remote_sha="$(
      git -C "$ROOT_DIR/$PREFIX" rev-parse --verify "${remote_ref}^{commit}" 2>/dev/null \
        || true
    )"
    [ "$remote_sha" = "$commit" ] || continue
    [ -n "$remote_branch" ] || continue
    if [ "$remote_branch" != "$DEFAULT_BRANCH" ]; then
      echo "$remote_branch"
      return 0
    fi
  done < <(git -C "$ROOT_DIR/$PREFIX" for-each-ref --format='%(refname:short)' refs/remotes/origin 2>/dev/null || true)

  while IFS="$(printf '\t')" read -r remote_sha remote_ref; do
    [ -n "$remote_sha" ] || continue
    [ -n "$remote_ref" ] || continue
    case "$remote_ref" in
      *"/HEAD")
        continue
        ;;
    esac
    remote_branch="${remote_ref#refs/heads/}"
    if [ "$remote_sha" = "$commit" ] && [ "$remote_branch" != "$DEFAULT_BRANCH" ] && [ -n "$remote_branch" ]; then
      echo "$remote_branch"
      return 0
    fi
  done < <(git -C "$ROOT_DIR/$PREFIX" ls-remote --heads origin 2>/dev/null || true)

  return 1
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
  return 0
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
  project_copy_source "$abs_source" "$abs_path" > "$abs_path"
  chmod --reference="$abs_source" "$abs_path"
}

project_copy_source() {
  local source="$1"
  local target="${2:-}"
  local projected=""
  local github_target=0
  if [[ "$target" == "$ROOT_DIR/.github/ISSUE_TEMPLATE/"* || "$target" == "$ROOT_DIR/.github/PULL_REQUEST_TEMPLATE/"* ]]; then
    github_target=1
  fi
  if ! is_submodule_prefix && [ "$github_target" -eq 0 ]; then
    cat "$source"
    return
  fi
  if is_submodule_prefix; then
    projected="$(perl -ne '
      if ($in_manifest || /\@dependency-start/) {
        print;
        $in_manifest = 1 if /\@dependency-start/;
        $in_manifest = 0 if /\@dependency-end/;
        next;
      }
      s{vendor/agent-canon/tools/}{__CANON_TOOLS__/}g;
      s{vendor/agent-canon/documents/}{__CANON_DOCUMENTS__/}g;
      s{vendor/agent-canon/templates/}{__CANON_TEMPLATES__/}g;
      s{vendor/agent-canon/issues/}{__CANON_ISSUES__/}g;
      s{documents/tools/}{__DOCUMENTS_TOOLS__/}g;
      s{tests/tools/}{__TESTS_TOOLS__/}g;
      s{tools/agent-canon/}{__PARENT_TOOLS__/}g;
      s{((?:\.\./)+)documents/}{$1vendor/agent-canon/documents/}g;
      s{((?:\.\./)+)issues/}{$1vendor/agent-canon/issues/}g;
      s{((?:\.\./)+)tools/}{$1tools/agent-canon/}g;
      s{(?<![A-Za-z0-9_./-])templates/}{vendor/agent-canon/templates/}g;
      s{(?<![A-Za-z0-9_./-])tools/}{tools/agent-canon/}g;
      s{__CANON_TOOLS__}{vendor/agent-canon/tools/}g;
      s{__CANON_DOCUMENTS__}{vendor/agent-canon/documents/}g;
      s{__CANON_TEMPLATES__}{vendor/agent-canon/templates/}g;
      s{__CANON_ISSUES__}{vendor/agent-canon/issues/}g;
      s{__DOCUMENTS_TOOLS__}{documents/tools/}g;
      s{__TESTS_TOOLS__}{tests/tools/}g;
      s{__PARENT_TOOLS__}{tools/agent-canon/}g;
      print;
    ' "$source")"
  else
    projected="$(cat "$source")"
  fi

  if [ "$github_target" -eq 1 ]; then
    if is_submodule_prefix; then
      printf '%s\n' "$projected" | perl -0pe '
        s{(@dependency-start.*?@dependency-end)}{
          my $block = $1;
          $block =~ s{\.\./\.\./\.\./operations/}{../../vendor/agent-canon/documents/operations/}g;
          $block =~ s{\.\./\.\./\.\./\.\./\.github/}{../}g;
          $block =~ s{\.\./\.\./\.\./\.github/}{../}g;
          $block =~ s{\.\./\.\./\.\./\.\./documents/}{../../vendor/agent-canon/documents/}g;
          $block =~ s{\.\./\.\./\.\./\.\./agents/}{../../agents/}g;
          $block =~ s{\.\./\.\./\.\./\.\./issues/}{../../vendor/agent-canon/issues/}g;
          $block =~ s{\.\./\.\./\.\./\.\./tools/}{../../tools/agent-canon/}g;
          $block =~ s{\.\./\.\./README\.md}{../../vendor/agent-canon/templates/documents/README.md}g;
          $block;
        }gse
      '
    else
      printf '%s\n' "$projected" | perl -0pe '
        s{(@dependency-start.*?@dependency-end)}{
          my $block = $1;
          $block =~ s{\.\./\.\./\.\./operations/}{../../documents/operations/}g;
          $block =~ s{\.\./\.\./\.\./\.\./\.github/}{../}g;
          $block =~ s{\.\./\.\./\.\./\.github/}{../}g;
          $block =~ s{\.\./\.\./\.\./\.\./(documents|agents|issues|tools)/}{../../$1/}g;
          $block =~ s{\.\./\.\./README\.md}{../../templates/documents/README.md}g;
          $block;
        }gse
      '
    fi
  else
    printf '%s\n' "$projected"
  fi
}

regular_path() {
  local path="$1"
  local source="${2:-}"
  local abs_path="$ROOT_DIR/$path"
  local abs_source=""
  if [ -e "$abs_path" ] && [ ! -L "$abs_path" ] \
    && { [ "$path" != ".vscode" ] || [ -d "$abs_path" ]; }; then
    if [ "$path" = ".devcontainer" ] && is_submodule_prefix; then
      prune_parent_devcontainer_artifacts
    fi
    return
  fi
  if [ -z "$source" ]; then
    if [ "$path" = ".devcontainer" ] && [ -e "$abs_path" ] && [ ! -L "$abs_path" ]; then
      prune_parent_devcontainer_artifacts
      return
    fi
    rm -rf "$abs_path"
    mkdir -p "$abs_path"
    if [ "$path" = ".devcontainer" ] && is_submodule_prefix; then
      prune_parent_devcontainer_artifacts
    fi
    return
  fi
  [ -n "$source" ] || die "regular path '$path' is missing or is a symlink and has no seed source"
  abs_source="$ROOT_DIR/$source"
  [ -e "$abs_source" ] || die "regular seed source '$source' does not exist"
  rm -rf "$abs_path"
  mkdir -p "$(dirname "$abs_path")"
  cp -a "$abs_source" "$abs_path"

  if [ "$path" = ".devcontainer" ] && is_submodule_prefix && [ -d "$abs_path" ]; then
    prune_parent_devcontainer_artifacts
  fi
}

prune_parent_devcontainer_artifacts() {
  local abs_path="$ROOT_DIR/.devcontainer"
  [ -d "$abs_path" ] || return 0
  rm -f \
    "$abs_path/bootstrap-shared-runtime.sh" \
    "$abs_path/finalize-shared-runtime.sh" \
    "$abs_path/generate-runtime-compose.sh" \
    "$abs_path/docker-compose.generated.yml" \
    "$abs_path/post-attach.sh" \
    "$abs_path/post-create.sh"
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

assert_parent_submodule_projection_ready() {
  local submodule_status=""
  local submodule_branch=""
  local parent_prefix_head=""
  local submodule_head=""

  if ! is_submodule_prefix; then
    return 0
  fi
  [ -d "$ROOT_DIR/$PREFIX" ] || die "prefix '$PREFIX' does not exist"

  submodule_status="$(git -C "$ROOT_DIR/$PREFIX" status --short --untracked-files=all)"
  if [ -n "$submodule_status" ]; then
    echo "agent_canon_parent_submodule=dirty"
    return 1
  fi

  submodule_branch="$(git -C "$ROOT_DIR/$PREFIX" symbolic-ref --quiet --short HEAD 2>/dev/null || true)"
  if [ -z "$submodule_branch" ]; then
    echo "agent_canon_parent_submodule=detached"
    return 2
  fi

  if [ "$submodule_branch" != "$DEFAULT_BRANCH" ]; then
    echo "agent_canon_parent_submodule=non_default_branch"
    return 4
  fi

  parent_prefix_head="$(git -C "$ROOT_DIR" rev-parse ":$PREFIX" 2>/dev/null || true)"
  submodule_head="$(git -C "$ROOT_DIR/$PREFIX" rev-parse HEAD)"
  if [ -z "$parent_prefix_head" ] || [ "$submodule_head" != "$parent_prefix_head" ]; then
    echo "agent_canon_parent_submodule=gitlink_mismatch"
    return 3
  fi

  echo "agent_canon_parent_submodule=projection_ready"
  return 0
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
  assert_parent_submodule_projection_ready || {
    local projection_rc="$?"
    local next_action=""
    if [ "$projection_rc" -eq 1 ]; then
      next_action="materialize_vendor_topic_commit_push_pr_or_use_workspace_fallback"
    elif [ "$projection_rc" -eq 2 ]; then
      next_action="request_user_direction_preserve_current_checkout_then_rerun_with_inline_git_authority_and_reason"
    elif [ "$projection_rc" -eq 4 ]; then
      next_action="checkout_${DEFAULT_BRANCH}_at_staged_gitlink_commit"
    else
      next_action="request_parent_vendor_source_readiness_and_rerun_link-root"
    fi
    echo "NEXT_ACTION=$next_action"
    echo "agent_canon_projection_requirements=parent_vendor_named_branch_and_gitlink_match_required"
    echo "AGENT_CANON_LINK_ROOT_PROJECTION_WARNING=${next_action}"
  }
  ensure_surface_sync_safe "$force"

  local spec=""
  # Materialize regular containers before child links. This converts legacy
  # whole-directory symlinks first, so child operations cannot delete files in
  # the AgentCanon source checkout through the old directory link.
  while IFS= read -r spec; do
    local path="${spec%%:*}"
    local source="${spec#*:}"
    regular_path "$path" "$source"
  done < <(build_regular_specs)

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

  if is_submodule_prefix; then
    prune_parent_devcontainer_artifacts
  fi

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
  local projection_rc=0

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
    local abs_path="$ROOT_DIR/$path"
    if [ -f "$abs_path" ]; then
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
    if [ -e "$abs_path" ] && [ ! -L "$abs_path" ] \
      && { [ "$path" != ".vscode" ] || [ -d "$abs_path" ]; }; then
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

  assert_parent_submodule_projection_ready || {
    projection_rc="$?"
    if [ "$projection_rc" -eq 1 ]; then
      echo "NEXT_ACTION=materialize_vendor_topic_commit_push_pr_or_use_workspace_fallback"
      echo "agent_canon_projection_scope=pin_root_projection_current_parent_checkout_only"
    elif [ "$projection_rc" -eq 2 ]; then
      echo "NEXT_ACTION=request_user_direction_preserve_current_checkout_then_rerun_with_inline_git_authority_and_reason"
      echo "agent_canon_projection_scope=pin_root_projection_current_parent_checkout_only"
    elif [ "$projection_rc" -eq 4 ]; then
      echo "NEXT_ACTION=checkout_${DEFAULT_BRANCH}_at_staged_gitlink_commit"
      echo "agent_canon_projection_scope=pin_root_projection_current_parent_checkout_only"
    else
      echo "NEXT_ACTION=request_parent_vendor_source_readiness_and_rerun_check"
      echo "agent_canon_projection_scope=pin_root_projection_current_parent_checkout_only"
    fi
    echo "agent_canon_projection_warning=projection_conditions_not_blocking_for_plan_checks"
  }

  if [ "$failed" -ne 0 ]; then
    [ "$failed" -ne 0 ] || return 0
    die "shared surface drift detected; set AGENT_CANON_COMMIT_REQUEST_EVIDENCE=evidence:<sha256-of-exact-authorization-evidence-bytes> and rerun 'bash tools/sync_agent_canon.sh link-root'"
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
  local -a owned_paths=("$PREFIX")
  local spec=""

  require_commit_provenance "commit-sync-paths"

  while IFS= read -r spec; do
    [ -n "$spec" ] || continue
    owned_paths+=("${spec%%:*}")
  done < <(
    {
      build_link_specs
      build_copy_specs
    }
  )
  while IFS= read -r spec; do
    [ -n "$spec" ] || continue
    if [ -e "$ROOT_DIR/$spec" ] || [ -L "$ROOT_DIR/$spec" ] || path_is_tracked "$spec"; then
      owned_paths+=("$spec")
    fi
  done < <(build_root_absent_paths)

  stage_sync_paths
  if git -C "$ROOT_DIR" diff --cached --quiet -- "${owned_paths[@]}"; then
    return
  fi

  GIT_AUTHOR_NAME="$COMMIT_AUTOMATION_AUTHOR_NAME" \
  GIT_AUTHOR_EMAIL="$COMMIT_AUTOMATION_AUTHOR_EMAIL" \
  GIT_COMMITTER_NAME="$COMMIT_AUTOMATION_AUTHOR_NAME" \
  GIT_COMMITTER_EMAIL="$COMMIT_AUTOMATION_AUTHOR_EMAIL" \
  git -C "$ROOT_DIR" commit --only \
    -m "chore: sync agent-canon snapshot" \
    --trailer "AgentCanon-Automation-Actor=agent-canon-sync" \
    --trailer "AgentCanon-Authority-Source=${AGENT_CANON_BRANCH_WORKTREE_AUTHORITY}" \
    --trailer "AgentCanon-Destructive-Authority=${AGENT_CANON_DESTRUCTIVE_GIT_AUTHORITY}" \
    --trailer "AgentCanon-Request-Evidence=${AGENT_CANON_COMMIT_REQUEST_EVIDENCE}" \
    --trailer "AgentCanon-Remote=$remote_sha" \
    --trailer "AgentCanon-Update-Method=$method" \
    --trailer "AgentCanon-Prefix=$PREFIX" \
    -- "${owned_paths[@]}"
}

automation_commit_message() {
  local remote_sha="$1"
  local method="$2"
  cat <<EOF
chore: sync agent-canon snapshot

AgentCanon-Automation-Actor: agent-canon-sync
AgentCanon-Authority-Source: ${AGENT_CANON_BRANCH_WORKTREE_AUTHORITY}
AgentCanon-Destructive-Authority: ${AGENT_CANON_DESTRUCTIVE_GIT_AUTHORITY}
AgentCanon-Request-Evidence: ${AGENT_CANON_COMMIT_REQUEST_EVIDENCE}
AgentCanon-Remote: ${remote_sha}
AgentCanon-Update-Method: ${method}
AgentCanon-Prefix: ${PREFIX}
EOF
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
  case "$route" in
    submodule_detached|submodule_non_default_branch) ;;
    *)
      echo "agent_canon_plan_apply_command=AGENT_CANON_COMMIT_REQUEST_EVIDENCE=evidence:<sha256-of-exact-authorization-evidence-bytes> bash tools/sync_agent_canon.sh ensure-latest $branch"
      ;;
  esac
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
  local submodule_worktree_branch=""
  local submodule_worktree_status="not_applicable"
  local submodule_deferred_ref=""

  if is_submodule_prefix; then
    prefix_mode="submodule"
    local_tree="$(submodule_commit)"
    local_split=""
    remote_url="$(submodule_remote_url)"
    if ! submodule_checkout_initialized; then
      print_plan_summary \
        "$branch" "$remote_url" "submodule" "" "" "$local_tree" \
        "" "$subtree_metadata" "submodule_checkout_uninitialized" "$dirty" "yes" "$prefix_mode" "no"
      print_submodule_plan_details "$local_tree" "" "uninitialized" ""
      echo "agent_canon_plan_status=approval_required"
      echo "NEXT_ACTION=$PROTECTED_GIT_NEXT_ACTION"
      return
    fi
    submodule_worktree_head="$(git -C "$ROOT_DIR/$PREFIX" rev-parse HEAD 2>/dev/null || true)"
    submodule_worktree_branch="$(
      git -C "$ROOT_DIR/$PREFIX" symbolic-ref --quiet --short HEAD 2>/dev/null || true
    )"
    if [ -n "$(git -C "$ROOT_DIR/$PREFIX" status --short --untracked-files=all)" ]; then
      submodule_worktree_status="dirty"
    else
      submodule_worktree_status="clean"
    fi
    if [ -n "$remote_url" ]; then
      remote_source="submodule"
    fi
  else
    ensure_prefix_exists
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

  if [ "$prefix_mode" = "submodule" ] && [ -z "$submodule_worktree_branch" ]; then
    route="submodule_detached"
    print_plan_summary \
      "$branch" "$remote_url" "$remote_source" "" "" "$local_tree" \
      "$local_split" "$subtree_metadata" "$route" "$dirty" "yes" "$prefix_mode" "$dirty_update_surface"
    print_submodule_plan_details \
      "$local_tree" "$submodule_worktree_head" "$submodule_worktree_status" ""
    echo "agent_canon_plan_status=blocked"
    echo "NEXT_ACTION=select_source_or_pin_owner_then_repair_detached_submodule"
  elif [ "$prefix_mode" = "submodule" ] \
    && [ "$submodule_worktree_status" = "clean" ] \
    && [ "$submodule_worktree_branch" != "$DEFAULT_BRANCH" ]; then
    route="submodule_non_default_branch"
    print_plan_summary \
      "$branch" "$remote_url" "$remote_source" "" "" "$local_tree" \
      "$local_split" "$subtree_metadata" "$route" "$dirty" "yes" "$prefix_mode" "$dirty_update_surface"
    print_submodule_plan_details \
      "$local_tree" "$submodule_worktree_head" "$submodule_worktree_status" ""
    echo "agent_canon_plan_status=blocked"
    echo "NEXT_ACTION=checkout_${DEFAULT_BRANCH}_at_staged_gitlink_commit"
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
    remote_sha="$(resolve_remote_branch_sha "$remote_url" "$branch")"
    ensure_remote_commit_object "$ROOT_DIR/$PREFIX" "$remote_url" "$remote_sha"
    remote_tree="$(git -C "$ROOT_DIR/$PREFIX" rev-parse "$remote_sha^{tree}")"
  else
    remote_sha="$(resolve_remote_branch_sha "$remote_url" "$branch")"
    ensure_remote_commit_object "$ROOT_DIR" "$remote_url" "$remote_sha"
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
  if [ -e "$ROOT_DIR/$PREFIX" ] || [ -n "$(prefix_git_mode)" ]; then
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
  local commit_message=""

  if ! has_subtree_metadata; then
    echo "agent_canon_subtree_pull=skipped_no_subtree_metadata"
    import_snapshot_preferring_tree_match "$local_split" "$local_tree" "$remote_sha" "snapshot_import_no_subtree_metadata"
    return
  fi

  pull_log="$(mktemp)"
  commit_message="$(automation_commit_message "$remote_sha" "subtree_pull")"
  if GIT_AUTHOR_NAME="$COMMIT_AUTOMATION_AUTHOR_NAME" \
    GIT_AUTHOR_EMAIL="$COMMIT_AUTOMATION_AUTHOR_EMAIL" \
    GIT_COMMITTER_NAME="$COMMIT_AUTOMATION_AUTHOR_NAME" \
    GIT_COMMITTER_EMAIL="$COMMIT_AUTOMATION_AUTHOR_EMAIL" \
    git -C "$ROOT_DIR" subtree pull --prefix="$PREFIX" "$REMOTE_NAME" "$remote_sha" \
    --squash --message="$commit_message" >"$pull_log" 2>&1; then
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
  local remote_sha=""
  require_clean_worktree
  ensure_remote "$remote_url"
  git -C "$ROOT_DIR" fetch --no-write-fetch-head "$REMOTE_NAME" "$branch"
  remote_sha="$(git -C "$ROOT_DIR" rev-parse --verify "$REMOTE_NAME/$branch^{commit}")"
  GIT_AUTHOR_NAME="$COMMIT_AUTOMATION_AUTHOR_NAME" \
  GIT_AUTHOR_EMAIL="$COMMIT_AUTOMATION_AUTHOR_EMAIL" \
  GIT_COMMITTER_NAME="$COMMIT_AUTOMATION_AUTHOR_NAME" \
  GIT_COMMITTER_EMAIL="$COMMIT_AUTOMATION_AUTHOR_EMAIL" \
    git -C "$ROOT_DIR" subtree add --prefix="$PREFIX" "$REMOTE_NAME" "$branch" \
    --squash --message="$(automation_commit_message "$remote_sha" "subtree_add")"
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
  remote_sha="$(resolve_remote_branch_sha "$REMOTE_NAME" "$branch")"
  ensure_remote_commit_object "$ROOT_DIR" "$REMOTE_NAME" "$remote_sha"
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
    local remote_url="" local_commit="" worktree_commit="" origin_sha=""
    local submodule_status="" submodule_remote_branch="" parent_pin_status="current"
    local index_entry="" staged_mode="" staged_sha="" staged_stage="" staged_path=""
    local applied_head="" applied_status=""
    local update_state=""

    submodule_checkout_initialized \
      || die "submodule '$PREFIX' checkout is uninitialized; initialize and attach $branch before updating"
    [ -z "$(git -C "$ROOT_DIR" ls-files --unmerged -- "$PREFIX")" ] \
      || die "submodule '$PREFIX' update blocked by an unmerged parent prefix"
    submodule_status="$(git -C "$ROOT_DIR/$PREFIX" status --porcelain=v1 --untracked-files=all)"
    [ -z "$submodule_status" ] || die "submodule '$PREFIX' update requires a clean worktree"
    remote_url="$(submodule_remote_url)"
    [ -n "$remote_url" ] || die "submodule '$PREFIX' has no .gitmodules url"
    local_commit="$(submodule_commit)"
    worktree_commit="$(git -C "$ROOT_DIR/$PREFIX" rev-parse HEAD)"
    submodule_remote_branch="$(submodule_remote_branch_for_head "$worktree_commit" || true)"
    remote_sha="$(resolve_remote_branch_sha "$remote_url" "$branch")"
    git -C "$ROOT_DIR/$PREFIX" fetch --no-write-fetch-head origin \
      "refs/heads/$branch:refs/remotes/origin/$branch" >/dev/null
    origin_sha="$(
      git -C "$ROOT_DIR/$PREFIX" rev-parse --verify "refs/remotes/origin/$branch^{commit}"
    )"
    [ "$origin_sha" = "$remote_sha" ] \
      || die "submodule '$PREFIX' origin/$branch '$origin_sha' does not match expected '$remote_sha'"
    if [ "$local_commit" != "$worktree_commit" ]; then
      parent_pin_status="stale"
      if [ -z "$submodule_remote_branch" ]; then
        echo "agent_canon_latest=local_submodule_worktree_differs_from_parent_pin"
        echo "agent_canon_latest_parent_pin_status=$parent_pin_status"
        die "submodule '$PREFIX' local HEAD differs from parent gitlink"
      fi
    fi

    echo "agent_canon_latest_submodule_local_state_checked=yes"
    echo "agent_canon_latest_submodule_local_state_source=$PREFIX"
    echo "agent_canon_latest_submodule_worktree_status=clean"
    if [ -n "$submodule_remote_branch" ]; then
      echo "agent_canon_latest_branch=$submodule_remote_branch"
      echo "agent_canon_latest_submodule_branch=$submodule_remote_branch"
      echo "agent_canon_latest_remote_branch=origin/$submodule_remote_branch"
    else
      echo "agent_canon_latest_branch=$branch"
      echo "agent_canon_latest_submodule_branch=$branch"
    fi
    echo "agent_canon_local_submodule=$local_commit"
    echo "agent_canon_worktree_submodule=$worktree_commit"
    echo "agent_canon_remote=$remote_sha"
    echo "agent_canon_latest_parent_pin_status=$parent_pin_status"
    if [ "$local_commit" = "$worktree_commit" ] && [ "$worktree_commit" = "$remote_sha" ]; then
      update_state="already_current_submodule"
    elif [ "$worktree_commit" = "$remote_sha" ]; then
      update_state="parent_pin_pending"
    elif [ -n "$submodule_remote_branch" ]; then
      update_state="deferred_branch_pr"
    else
      update_state="updating_submodule"
    fi
    if [ "$update_state" = "updating_submodule" ]; then
      ensure_surface_sync_safe
    fi
    echo "agent_canon_latest=$update_state"
    if [ "$update_state" = "deferred_branch_pr" ]; then
      cmd_link_root 1
      return
    fi

    git -C "$ROOT_DIR/$PREFIX" merge --ff-only "origin/$branch" >/dev/null
    git -C "$ROOT_DIR" add -A -- "$PREFIX"
    index_entry="$(git -C "$ROOT_DIR" ls-files --stage -- "$PREFIX")"
    read -r staged_mode staged_sha staged_stage staged_path <<<"$index_entry"
    if [ "$(printf '%s\n' "$index_entry" | awk 'NF { count += 1 } END { print count + 0 }')" -ne 1 ] \
      || [ "$staged_mode" != "160000" ] || [ "$staged_stage" != "0" ] \
      || [ "$staged_path" != "$PREFIX" ] || [ "$staged_sha" != "$remote_sha" ]; then
      die "submodule '$PREFIX' update did not produce the expected stage-0 gitlink"
    fi
    applied_head="$(git -C "$ROOT_DIR/$PREFIX" rev-parse HEAD)"
    applied_status="$(git -C "$ROOT_DIR/$PREFIX" status --porcelain=v1 --untracked-files=all)"
    [ "$applied_head" = "$staged_sha" ] && [ -z "$applied_status" ] \
      || die "submodule '$PREFIX' staged-pin readback failed"
    echo "agent_canon_latest_submodule_origin_main=$origin_sha"
    if [ -n "$submodule_remote_branch" ]; then
      echo "agent_canon_latest_submodule_applied_branch=$submodule_remote_branch"
      echo "agent_canon_latest_submodule_applied_remote_branch=origin/$submodule_remote_branch"
    else
      echo "agent_canon_latest_submodule_applied_branch=$branch"
      echo "agent_canon_latest_submodule_applied_remote_branch=origin/$branch"
    fi
    echo "agent_canon_latest_submodule_applied_head=$applied_head"
    echo "agent_canon_latest_submodule_staged_pin=$staged_sha"
    echo "agent_canon_latest_submodule_applied_upstream=origin/${submodule_remote_branch:-$branch}"
    echo "agent_canon_latest_submodule_applied_status=clean"

    if [ "$update_state" = "already_current_submodule" ]; then
      cmd_link_root 1
      return
    fi
    if [ "$update_state" = "parent_pin_pending" ]; then
      cmd_link_root 1
      commit_sync_paths_if_needed "$remote_sha" "submodule_parent_pin"
      return
    fi
    if [ "$update_state" = "deferred_branch_pr" ]; then
      cmd_link_root 1
      return
    fi
    cmd_link_root
    commit_sync_paths_if_needed "$remote_sha" "submodule_update"
    return
  fi

  ensure_existing_remote_or_default
  remote_sha="$(resolve_remote_branch_sha "$REMOTE_NAME" "$branch")"
  ensure_remote_commit_object "$ROOT_DIR" "$REMOTE_NAME" "$remote_sha"
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
    local abs_path="$ROOT_DIR/$path"
    if [ -f "$abs_path" ]; then
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
    add|submodule-add|pull|ensure-latest|link-root|snapshot)
      require_commit_provenance "$subcommand"
      ;;
  esac
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
