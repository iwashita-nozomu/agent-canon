#!/usr/bin/env bash
# @dependency-start
# contract tool
# responsibility Provides sync agent canon repository automation.
# upstream design ../documents/agent-canon/agent-canon-update-route.md canonical update materialization acceptance
# upstream design ../documents/rule/repository-topic-clone.md generic repository source clone lifecycle
# upstream design ../documents/rule/dependency-module-changes.md dependency source branch and projection ownership
# upstream design ../documents/runtime/SHARED_RUNTIME_SURFACES.md shared surface ownership policy
# upstream design ../documents/runtime/shared-runtime-surfaces.toml machine-readable surface manifest
# upstream implementation ./agent_tools/surface_manifest.py renders projection and update-transition specs
# downstream implementation ../tests/tools/test_update_agent_canon.py verifies sync/update behavior
# downstream implementation ../tests/tools/test_update_agent_canon_surface_migration.py verifies bounded migration
# downstream implementation ../test/testrunner.sh exposes the source-owned public test route
# @dependency-end
set -euo pipefail
export GIT_TERMINAL_PROMPT="${GIT_TERMINAL_PROMPT:-0}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
source "${SCRIPT_DIR}/lib/git_authority.sh"
source "${SCRIPT_DIR}/lib/update_materialization.sh"
SUPERPROJECT_DIR="$(git -C "$SCRIPT_DIR" rev-parse --show-superproject-working-tree 2>/dev/null || true)"
if [ -n "$SUPERPROJECT_DIR" ]; then
  ROOT_DIR="$SUPERPROJECT_DIR"
else
  ROOT_DIR="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel)"
fi
AGENT_CANON_SOURCE_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd -P)"
SOURCE_GIT_TOPLEVEL="$(git -C "${AGENT_CANON_SOURCE_ROOT}" rev-parse --show-toplevel 2>/dev/null || true)"
if [[ "${SOURCE_GIT_TOPLEVEL}" != "${AGENT_CANON_SOURCE_ROOT}" ]]; then
  AGENT_CANON_SOURCE_ROOT="${ROOT_DIR}"
fi
AGENT_CANON_BOUNDARY_SCRIPT="${SCRIPT_DIR}/agent_tools/parent_root_side_effects.py"
if [[ -z "${AGENT_CANON_SIDE_EFFECT_HANDOFF:-}" ]]; then
  invocation_script="$(realpath -e "${BASH_SOURCE[0]}" 2>/dev/null || true)"
  if [[ -z "${invocation_script}" || ! -f "${invocation_script}" ]]; then
    echo "AGENT_CANON_SYNC=fail reason=invocation_script_missing" >&2
    exit 2
  fi
  exec python3 "${AGENT_CANON_BOUNDARY_SCRIPT}" public-exec \
    --invocation-script "${invocation_script}" \
    --purpose agent-canon-sync-script \
    -- bash "${invocation_script}" "$@"
fi
PARENT_ROOT_DIR="${AGENT_CANON_SIDE_EFFECT_PARENT_ROOT:-}"
if [[ -z "${PARENT_ROOT_DIR}" ]]; then
  echo "AGENT_CANON_SYNC=fail reason=side_effect_session_missing" >&2
  exit 2
fi
PARENT_ROOT_DIR="$(cd "${PARENT_ROOT_DIR}" && pwd -P)"

CANON_PARENT_TMP_CANDIDATE="${AGENT_CANON_PARENT_TMPDIR:-$PARENT_ROOT_DIR/.agent-canon/tmp/sync}"
CANON_PARENT_TMPDIR="$(python3 "${SCRIPT_DIR}/agent_tools/parent_root_side_effects.py" \
  ensure-dir --root "$PARENT_ROOT_DIR" --candidate "$CANON_PARENT_TMP_CANDIDATE" --purpose agent-canon-sync)"
export TMPDIR="$CANON_PARENT_TMPDIR"
parent_ensure_dir() {
  python3 "${SCRIPT_DIR}/agent_tools/parent_root_side_effects.py" \
    ensure-dir --root "$PARENT_ROOT_DIR" --candidate "$1" --purpose "${2:-agent-canon-sync}"
}
parent_temp_dir() {
  python3 "${SCRIPT_DIR}/agent_tools/parent_root_side_effects.py" \
    temp-dir --root "$PARENT_ROOT_DIR" --candidate "$1" --prefix "$2" --purpose "${3:-agent-canon-sync}"
}
parent_write_file() {
  local candidate="$1" content="${2-}"
  printf '%s' "$content" | python3 "${SCRIPT_DIR}/agent_tools/parent_root_side_effects.py" \
    write --root "$PARENT_ROOT_DIR" --candidate "$candidate" --purpose "${3:-agent-canon-sync}" >/dev/null
}
parent_remove_file() {
  python3 "${SCRIPT_DIR}/agent_tools/parent_root_side_effects.py" \
    remove-file --root "$PARENT_ROOT_DIR" --candidate "$1" --purpose "${2:-agent-canon-sync}" >/dev/null
}
parent_remove_tree() {
  python3 "${SCRIPT_DIR}/agent_tools/parent_root_side_effects.py" \
    remove-tree --root "$PARENT_ROOT_DIR" --candidate "$1" --purpose "${2:-agent-canon-sync}" >/dev/null
}
parent_remove_empty_dir() {
  python3 "${SCRIPT_DIR}/agent_tools/parent_root_side_effects.py" \
    remove-empty-dir --root "$PARENT_ROOT_DIR" --candidate "$1" --purpose "${2:-agent-canon-sync}" >/dev/null
}
parent_checkout_index() {
  python3 "${SCRIPT_DIR}/agent_tools/parent_root_side_effects.py" \
    checkout-index --root "$PARENT_ROOT_DIR" --repository "$ROOT_DIR" --index-path "$1" \
    --candidate "$2" --purpose "${3:-agent-canon-sync}" >/dev/null
}
parent_copy_file() {
  python3 "${SCRIPT_DIR}/agent_tools/parent_root_side_effects.py" \
    copy --root "$PARENT_ROOT_DIR" --source "$1" --candidate "$2" --purpose "${3:-agent-canon-sync}" >/dev/null
}
parent_capture_subprocess() {
  local candidate="$1" purpose="$2"
  shift 2
  python3 "${SCRIPT_DIR}/agent_tools/parent_root_side_effects.py" \
    capture-subprocess --root "$PARENT_ROOT_DIR" --candidate "$candidate" \
    --purpose "$purpose" -- "$@"
}
parent_move_path() {
  python3 "${SCRIPT_DIR}/agent_tools/parent_root_side_effects.py" \
    move --root "$PARENT_ROOT_DIR" --source "$1" --candidate "$2" --purpose "${3:-agent-canon-sync}" >/dev/null
}
parent_symlink() {
  python3 "${SCRIPT_DIR}/agent_tools/parent_root_side_effects.py" \
    symlink --root "$PARENT_ROOT_DIR" --target "$1" --candidate "$2" --purpose "${3:-agent-canon-sync}" >/dev/null
}
PREFIX="${AGENT_CANON_PREFIX:-vendor/agent-canon}"
if [ "$PREFIX" = "." ]; then
  PUBLIC_SYNC_COMMAND="bash tools/sync_agent_canon.sh"
else
  PUBLIC_SYNC_COMMAND="PYTHONPATH=${PREFIX}/tools:tools python3 -m agent_tools.agent_canon_source_root exec tools/sync_agent_canon.sh"
fi
REMOTE_NAME="${AGENT_CANON_REMOTE_NAME:-agent-canon}"
DEFAULT_BRANCH="${AGENT_CANON_BRANCH:-main}"
FORCE_RELINK="${AGENT_CANON_FORCE_RELINK:-0}"
PLAN_REMOTE_OVERRIDE_URL="${AGENT_CANON_PLAN_REMOTE_URL:-}"
CANONICAL_AGENT_CANON_REMOTE_URL="${AGENT_CANON_GITHUB_REMOTE_URL:-https://github.com/iwashita-nozomu/agent-canon.git}"
SURFACE_MANIFEST="${AGENT_CANON_SURFACE_MANIFEST:-documents/runtime/shared-runtime-surfaces.toml}"
PROTECTED_GIT_NEXT_ACTION="request_explicit_user_approval_then_rerun_same_command_with_inline_git_authority_and_reason"
BRANCH_WORKTREE_NEXT_ACTION="request_branch_or_worktree_creation_authority_then_rerun_same_command_with_inline_git_authority_and_reason"
COMMIT_AUTOMATION_AUTHOR_NAME="AgentCanon Sync Automation"
COMMIT_AUTOMATION_AUTHOR_EMAIL="agent-canon-sync@automation.invalid"
COMMIT_PROVENANCE_NEXT_ACTION="set AGENT_CANON_COMMIT_REQUEST_EVIDENCE=evidence:<64 lowercase hex> and rerun the same command"
ACTIVE_ROOT_COPY_TRANSITION_ID=""
declare -a ROOT_COPY_TRANSITION_CANDIDATES=()
declare -a ROOT_COPY_TRANSITION_REMOVED_PATHS=()

# Readback facts are deliberately kept in process globals.  Plan/attach callers
# invoke the resolver directly so a failed remote probe can be rendered in the
# same complete plan record before its non-zero status is returned.
REMOTE_RESOLUTION_STATUS="not_attempted"
REMOTE_RESOLUTION_ERROR_KIND="none"
REMOTE_RESOLUTION_ERROR_DETAIL=""
REMOTE_RESOLUTION_URL=""
REMOTE_RESOLUTION_BRANCH=""
REMOTE_RESOLUTION_SHA=""
REMOTE_RESOLUTION_OUTPUT=""
REMOTE_OBJECT_STATUS="not_attempted"
REMOTE_OBJECT_ERROR_KIND="none"
REMOTE_OBJECT_ERROR_DETAIL=""
REMOTE_OBJECT_SHA=""
REMOTE_OBJECT_FETCH_ATTEMPTED="no"
REMOTE_TRACKING_STATUS="not_attempted"
REMOTE_TRACKING_ERROR_KIND="none"
REMOTE_TRACKING_ERROR_DETAIL=""
REMOTE_TRACKING_EXPECTED_SHA=""
REMOTE_TRACKING_FETCHED_SHA=""
REMOTE_TRACKING_URL=""
REMOTE_TRACKING_BRANCH=""
REMOTE_SNAPSHOT_START_SHA=""
REMOTE_SNAPSHOT_END_SHA=""
REMOTE_SNAPSHOT_SELECTED_SHA=""
REMOTE_SNAPSHOT_COHERENCE="not_attempted"
REMOTE_PROBE_STATUS="not_attempted"
REMOTE_PROBE_ERROR_KIND="none"
REMOTE_PROBE_ERROR_DETAIL=""
REMOTE_PROBE_TREE=""
REMOTE_PROBE_RESULT_TREE=""
REMOTE_PROBE_HISTORY_STATE="unknown"
REMOTE_PROBE_COLLISION_PATH=""
REMOTE_PROBE_CLEANUP_STATUS="not_attempted"
REMOTE_PROBE_PATH=""
REMOTE_PROBE_OBJECTS=""
PLAN_REMOTE_ALTERNATES_PREVIOUS=""
ATTACH_TXN_DIR=""
ATTACH_TXN_GIT_DIR=""
ATTACH_TXN_OBJECTS_DIR=""
ATTACH_TXN_FETCH_HEAD_PATH=""
ATTACH_TXN_BEFORE_HEAD=""
ATTACH_TXN_BEFORE_MAIN_SHA=""
ATTACH_TXN_BEFORE_ORIGIN_SHA=""
ATTACH_TXN_BEFORE_STATUS=""
ATTACH_TXN_BEFORE_FETCH_EXISTS="no"
ATTACH_TXN_RESTORE_STATUS="not_attempted"
ATTACH_TXN_RESTORE_ERROR_KIND="none"
ATTACH_TXN_RESTORE_ERROR_DETAIL=""
ATTACH_TXN_CLEANUP_STATUS="not_attempted"
ATTACH_TXN_CLEANUP_ERROR_DETAIL=""
SUBMODULE_STAGE0_STATUS="not_checked"
SUBMODULE_STAGE0_MODE="<unavailable>"
SUBMODULE_STAGE0_SHA=""
SUBMODULE_STAGE0_STAGE="<unavailable>"
SUBMODULE_STAGE0_PATH="<unavailable>"
SUBMODULE_STAGE0_ERROR_KIND="none"
SUBMODULE_STAGE0_ERROR_DETAIL=""

usage() {
  cat <<EOF
Usage:
  $PUBLIC_SYNC_COMMAND plan [branch]
  AGENT_CANON_COMMIT_REQUEST_EVIDENCE=evidence:<sha256-of-exact-authorization-evidence-bytes> $PUBLIC_SYNC_COMMAND link-root
  $PUBLIC_SYNC_COMMAND check
  AGENT_CANON_COMMIT_REQUEST_EVIDENCE=evidence:<sha256-of-exact-authorization-evidence-bytes> $PUBLIC_SYNC_COMMAND submodule-add <remote-url> [branch]
  AGENT_CANON_COMMIT_REQUEST_EVIDENCE=evidence:<sha256-of-exact-authorization-evidence-bytes> $PUBLIC_SYNC_COMMAND ensure-latest [branch]
  $PUBLIC_SYNC_COMMAND status

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

protected_git_authority_failure() {
  local mode="$1"
  git_authority_emit_failure \
    "$mode" "$PROTECTED_GIT_NEXT_ACTION" "$BRANCH_WORKTREE_NEXT_ACTION" \
    "protected AgentCanon update requires inherited"
  die "$GIT_AUTHORITY_FAILURE_DETAIL"
}

require_commit_provenance() {
  local mode="$1"
  if git_authority_check_commit_provenance "$mode"; then
    return 0
  fi

  if ! git_authority_check_protected_git_authority "$mode"; then
    protected_git_authority_failure "$mode"
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
  local malformed_count=0

  REMOTE_RESOLUTION_STATUS="not_attempted"
  REMOTE_RESOLUTION_ERROR_KIND="none"
  REMOTE_RESOLUTION_ERROR_DETAIL=""
  REMOTE_RESOLUTION_URL="$remote"
  REMOTE_RESOLUTION_BRANCH="$branch"
  REMOTE_RESOLUTION_SHA=""
  REMOTE_RESOLUTION_OUTPUT=""
  if ! output="$(git ls-remote --exit-code "$remote" "$expected_ref" 2>&1)"; then
    REMOTE_RESOLUTION_STATUS="unreachable"
    REMOTE_RESOLUTION_ERROR_KIND="ls_remote_failed"
    REMOTE_RESOLUTION_ERROR_DETAIL="$output"
    REMOTE_RESOLUTION_OUTPUT="$output"
    return 1
  fi
  REMOTE_RESOLUTION_OUTPUT="$output"
  while IFS=$' \t' read -r candidate_sha candidate_ref; do
    [ -n "$candidate_sha" ] || continue
    if [ "$candidate_ref" != "$expected_ref" ]; then
      continue
    fi
    match_count=$((match_count + 1))
    resolved_sha="${candidate_sha,,}"
    if ! [[ "$candidate_sha" =~ ^[0-9a-fA-F]{40}([0-9a-fA-F]{24})?$ ]]; then
      malformed_count=$((malformed_count + 1))
    fi
  done <<<"$output"
  if [ "$match_count" -gt 1 ]; then
    REMOTE_RESOLUTION_STATUS="ambiguous"
    REMOTE_RESOLUTION_ERROR_KIND="matching_ref_count"
    REMOTE_RESOLUTION_ERROR_DETAIL="remote branch '$remote#$branch' resolved with $match_count matching records"
    return 1
  fi
  if [ "$match_count" -eq 1 ] && [ "$malformed_count" -ne 0 ]; then
    REMOTE_RESOLUTION_STATUS="malformed"
    REMOTE_RESOLUTION_ERROR_KIND="invalid_object_id"
    REMOTE_RESOLUTION_ERROR_DETAIL="remote branch '$remote#$branch' returned invalid object id '$resolved_sha'"
    return 1
  fi
  if [ "$match_count" -eq 0 ]; then
    REMOTE_RESOLUTION_STATUS="unresolved"
    REMOTE_RESOLUTION_ERROR_KIND="missing_matching_ref"
    REMOTE_RESOLUTION_ERROR_DETAIL="remote branch '$remote#$branch' returned no matching '$expected_ref' record"
    return 1
  fi
  REMOTE_RESOLUTION_STATUS="resolved"
  REMOTE_RESOLUTION_SHA="$resolved_sha"
  return 0
}

ensure_remote_commit_object() {
  local repo="$1"
  local remote="$2"
  local sha="$3"
  local resolved=""

  REMOTE_OBJECT_STATUS="not_attempted"
  REMOTE_OBJECT_ERROR_KIND="none"
  REMOTE_OBJECT_ERROR_DETAIL=""
  REMOTE_OBJECT_SHA="$sha"
  REMOTE_OBJECT_FETCH_ATTEMPTED="no"
  if git -C "$repo" cat-file -e "$sha^{commit}" 2>/dev/null; then
    REMOTE_OBJECT_STATUS="available"
  else
    REMOTE_OBJECT_FETCH_ATTEMPTED="yes"
    local fetch_output=""
    if ! fetch_output="$(git -C "$repo" fetch --no-write-fetch-head "$remote" "$sha" 2>&1)"; then
      REMOTE_OBJECT_STATUS="unavailable"
      REMOTE_OBJECT_ERROR_KIND="fetch_failed"
      REMOTE_OBJECT_ERROR_DETAIL="$fetch_output"
      return 1
    fi
    resolved="$(git -C "$repo" rev-parse --verify "$sha^{commit}" 2>/dev/null || true)"
    if [ "$resolved" != "$sha" ]; then
      REMOTE_OBJECT_STATUS="unavailable"
      REMOTE_OBJECT_ERROR_KIND="readback_mismatch"
      REMOTE_OBJECT_ERROR_DETAIL="resolved object '${resolved:-<unavailable>}' does not match '$sha'"
      return 1
    fi
    REMOTE_OBJECT_STATUS="available"
  fi
  return 0
}

plan_remote_probe_fetch() {
  local probe="$1"
  local remote="$2"
  local sha="$3"
  local fetch_output=""
  local resolved=""

  if ! fetch_output="$(git -C "$probe" fetch --no-write-fetch-head "$remote" "$sha" 2>&1)"; then
    REMOTE_PROBE_STATUS="object_unavailable"
    REMOTE_PROBE_ERROR_KIND="probe_fetch_failed"
    REMOTE_PROBE_ERROR_DETAIL="$fetch_output"
    REMOTE_OBJECT_STATUS="unavailable"
    REMOTE_OBJECT_ERROR_KIND="probe_fetch_failed"
    REMOTE_OBJECT_ERROR_DETAIL="$fetch_output"
    REMOTE_OBJECT_SHA="$sha"
    REMOTE_OBJECT_FETCH_ATTEMPTED="yes"
    return 1
  fi
  resolved="$(git -C "$probe" rev-parse --verify "$sha^{commit}" 2>/dev/null || true)"
  if [ "$resolved" != "$sha" ]; then
    REMOTE_PROBE_STATUS="object_unavailable"
    REMOTE_PROBE_ERROR_KIND="probe_readback_mismatch"
    REMOTE_PROBE_ERROR_DETAIL="probe resolved object '${resolved:-<unavailable>}' does not match '$sha'"
    REMOTE_OBJECT_STATUS="unavailable"
    REMOTE_OBJECT_ERROR_KIND="probe_readback_mismatch"
    REMOTE_OBJECT_ERROR_DETAIL="$REMOTE_PROBE_ERROR_DETAIL"
    REMOTE_OBJECT_SHA="$sha"
    REMOTE_OBJECT_FETCH_ATTEMPTED="yes"
    return 1
  fi
  REMOTE_OBJECT_STATUS="available"
  REMOTE_OBJECT_ERROR_KIND="none"
  REMOTE_OBJECT_ERROR_DETAIL=""
  REMOTE_OBJECT_SHA="$sha"
  REMOTE_OBJECT_FETCH_ATTEMPTED="yes"
  return 0
}

plan_remote_probe() {
  local repo="$1"
  local remote="$2"
  local branch="$3"
  local current_sha="${4:-}"
  local probe=""
  local source_objects=""
  local probe_objects=""
  local start_sha=""
  local end_sha=""
  local selected_sha=""
  local third_sha=""
  local remote_tree=""
  local result_tree=""
  local result_rc=0
  local collision_path=""
  local collision_rc=1
  local tracking_sha=""

  REMOTE_SNAPSHOT_START_SHA=""
  REMOTE_SNAPSHOT_END_SHA=""
  REMOTE_SNAPSHOT_SELECTED_SHA=""
  REMOTE_SNAPSHOT_COHERENCE="not_attempted"
  REMOTE_PROBE_STATUS="not_attempted"
  REMOTE_PROBE_ERROR_KIND="none"
  REMOTE_PROBE_ERROR_DETAIL=""
  REMOTE_PROBE_TREE=""
  REMOTE_PROBE_RESULT_TREE=""
  REMOTE_PROBE_HISTORY_STATE="unknown"
  REMOTE_PROBE_COLLISION_PATH=""
  REMOTE_PROBE_CLEANUP_STATUS="not_attempted"
  REMOTE_PROBE_PATH=""
  REMOTE_PROBE_OBJECTS=""
  REMOTE_OBJECT_STATUS="not_attempted"
  REMOTE_OBJECT_ERROR_KIND="none"
  REMOTE_OBJECT_ERROR_DETAIL=""
  REMOTE_OBJECT_SHA=""
  REMOTE_OBJECT_FETCH_ATTEMPTED="no"

  if ! resolve_remote_branch_sha "$remote" "$branch"; then
    REMOTE_PROBE_STATUS="resolution_failed"
    REMOTE_PROBE_ERROR_KIND="$REMOTE_RESOLUTION_ERROR_KIND"
    REMOTE_PROBE_ERROR_DETAIL="$REMOTE_RESOLUTION_ERROR_DETAIL"
    return 1
  fi
  start_sha="$REMOTE_RESOLUTION_SHA"
  REMOTE_SNAPSHOT_START_SHA="$start_sha"
  REMOTE_SNAPSHOT_SELECTED_SHA="$start_sha"

  source_objects="$(git -C "$repo" rev-parse --git-path objects 2>/dev/null || true)"
  if [ -z "$source_objects" ]; then
    REMOTE_PROBE_STATUS="probe_setup_failed"
    REMOTE_PROBE_ERROR_KIND="source_object_database_unavailable"
    REMOTE_PROBE_ERROR_DETAIL="source repository object database could not be resolved"
    return 1
  fi
  if [[ "$source_objects" != /* ]]; then
    source_objects="$repo/$source_objects"
  fi
  source_objects="$(realpath -m -- "$source_objects" 2>/dev/null || true)"
  if [ ! -d "$source_objects" ]; then
    REMOTE_PROBE_STATUS="probe_setup_failed"
    REMOTE_PROBE_ERROR_KIND="source_object_database_missing"
    REMOTE_PROBE_ERROR_DETAIL="source object database '$source_objects' is unavailable"
    return 1
  fi

  probe="$(parent_temp_dir "$CANON_PARENT_TMPDIR" remote-probe)" || {
    REMOTE_PROBE_STATUS="probe_setup_failed"
    REMOTE_PROBE_ERROR_KIND="probe_directory_failed"
    REMOTE_PROBE_ERROR_DETAIL="could not allocate a parent-owned disposable probe"
    return 1
  }
  REMOTE_PROBE_PATH="$probe"
  if ! git init --bare "$probe" >/dev/null 2>&1; then
    REMOTE_PROBE_STATUS="probe_setup_failed"
    REMOTE_PROBE_ERROR_KIND="probe_init_failed"
    REMOTE_PROBE_ERROR_DETAIL="could not initialize disposable probe '$probe'"
    plan_remote_probe_abort 1 || return $?
  fi
  probe_objects="$(git -C "$probe" rev-parse --git-path objects 2>/dev/null || true)"
  if [[ "$probe_objects" != /* ]]; then
    probe_objects="$probe/$probe_objects"
  fi
  REMOTE_PROBE_OBJECTS="$probe_objects"
  if ! parent_ensure_dir "$probe_objects/info" >/dev/null; then
    REMOTE_PROBE_STATUS="probe_setup_failed"
    REMOTE_PROBE_ERROR_KIND="probe_objects_directory_failed"
    REMOTE_PROBE_ERROR_DETAIL="could not create disposable probe object metadata"
    plan_remote_probe_abort 1 || return $?
  fi
  if ! parent_write_file "$probe_objects/info/alternates" "$source_objects"$'\n' "agent-canon-plan-probe"; then
    REMOTE_PROBE_STATUS="probe_setup_failed"
    REMOTE_PROBE_ERROR_KIND="probe_alternates_write_failed"
    REMOTE_PROBE_ERROR_DETAIL="could not configure source object alternates in disposable probe"
    plan_remote_probe_abort 1 || return $?
  fi

  if ! plan_remote_probe_fetch "$probe" "$remote" "$start_sha"; then
    plan_remote_probe_abort 1 || return $?
  fi
  selected_sha="$start_sha"
  end_sha="$start_sha"
  REMOTE_SNAPSHOT_COHERENCE="stable"

  if resolve_remote_branch_sha "$remote" "$branch"; then
    end_sha="$REMOTE_RESOLUTION_SHA"
    if [ "$end_sha" != "$start_sha" ]; then
      if plan_remote_probe_fetch "$probe" "$remote" "$end_sha"; then
        if GIT_ALTERNATE_OBJECT_DIRECTORIES="$probe_objects" \
          git -C "$probe" merge-base --is-ancestor "$start_sha" "$end_sha"; then
          selected_sha="$end_sha"
          REMOTE_SNAPSHOT_COHERENCE="advanced"
          if resolve_remote_branch_sha "$remote" "$branch"; then
            third_sha="$REMOTE_RESOLUTION_SHA"
            if [ "$third_sha" != "$end_sha" ]; then
              selected_sha="$start_sha"
              REMOTE_SNAPSHOT_COHERENCE="advanced_during_probe"
            fi
            end_sha="$third_sha"
          else
            selected_sha="$start_sha"
            REMOTE_SNAPSHOT_COHERENCE="advanced_during_probe"
            end_sha="$REMOTE_SNAPSHOT_START_SHA"
          fi
        fi
        if [ "$selected_sha" = "$start_sha" ]; then
          REMOTE_SNAPSHOT_COHERENCE="rewound_or_unrelated"
        fi
      else
        plan_remote_probe_abort 1 || return $?
      fi
    fi
  else
    REMOTE_PROBE_STATUS="resolution_failed"
    REMOTE_PROBE_ERROR_KIND="$REMOTE_RESOLUTION_ERROR_KIND"
    REMOTE_PROBE_ERROR_DETAIL="$REMOTE_RESOLUTION_ERROR_DETAIL"
    plan_remote_probe_abort 1 || return $?
  fi
  REMOTE_SNAPSHOT_END_SHA="$end_sha"
  REMOTE_SNAPSHOT_SELECTED_SHA="$selected_sha"
  REMOTE_RESOLUTION_STATUS="resolved"
  REMOTE_RESOLUTION_SHA="$selected_sha"
  REMOTE_TRACKING_EXPECTED_SHA="$selected_sha"
  REMOTE_TRACKING_URL="$remote"
  REMOTE_TRACKING_BRANCH="$branch"
  remote_tree="$(git -C "$probe" rev-parse "$selected_sha^{tree}" 2>/dev/null || true)"
  if [ -z "$remote_tree" ]; then
    REMOTE_PROBE_STATUS="object_unavailable"
    REMOTE_PROBE_ERROR_KIND="probe_tree_readback_failed"
    REMOTE_PROBE_ERROR_DETAIL="probe tree readback failed for '$selected_sha'"
    REMOTE_OBJECT_STATUS="unavailable"
    REMOTE_OBJECT_ERROR_KIND="probe_tree_readback_failed"
    REMOTE_OBJECT_ERROR_DETAIL="$REMOTE_PROBE_ERROR_DETAIL"
    plan_remote_probe_abort 1 || return $?
  fi
  REMOTE_PROBE_TREE="$remote_tree"
  tracking_sha="$(git -C "$repo" rev-parse --verify "refs/remotes/origin/$branch^{commit}" 2>/dev/null || true)"
  if [ -z "$tracking_sha" ]; then
    REMOTE_TRACKING_STATUS="missing"
    REMOTE_TRACKING_ERROR_KIND="tracking_ref_missing"
    REMOTE_TRACKING_ERROR_DETAIL="local refs/remotes/origin/$branch is absent; attach may acquire it"
    REMOTE_TRACKING_FETCHED_SHA=""
  elif [ "$tracking_sha" = "$selected_sha" ]; then
    REMOTE_TRACKING_STATUS="matched"
    REMOTE_TRACKING_ERROR_KIND="none"
    REMOTE_TRACKING_ERROR_DETAIL=""
    REMOTE_TRACKING_FETCHED_SHA="$tracking_sha"
  elif git -C "$probe" merge-base --is-ancestor "$tracking_sha" "$selected_sha"; then
    REMOTE_TRACKING_STATUS="remote_advanced"
    REMOTE_TRACKING_ERROR_KIND="none"
    REMOTE_TRACKING_ERROR_DETAIL="local origin/$branch is an ancestor of selected remote main"
    REMOTE_TRACKING_FETCHED_SHA="$tracking_sha"
  else
    REMOTE_TRACKING_STATUS="mismatch"
    if git -C "$probe" merge-base --is-ancestor "$selected_sha" "$tracking_sha"; then
      REMOTE_TRACKING_ERROR_KIND="remote_rewind"
    else
      REMOTE_TRACKING_ERROR_KIND="unrelated_history"
    fi
    REMOTE_TRACKING_ERROR_DETAIL="local origin/$branch '$tracking_sha' is not an ancestor of selected remote '$selected_sha'"
    REMOTE_TRACKING_FETCHED_SHA="$tracking_sha"
  fi
  if [ "$REMOTE_SNAPSHOT_COHERENCE" = "rewound_or_unrelated" ]; then
    REMOTE_TRACKING_STATUS="mismatch"
    REMOTE_TRACKING_ERROR_KIND="remote_snapshot_rewound_or_unrelated"
    REMOTE_TRACKING_ERROR_DETAIL="remote changed from snapshot '$start_sha' to unrelated or rewound '$end_sha' during probe"
  fi
  if [ "$REMOTE_TRACKING_STATUS" = "mismatch" ]; then
    REMOTE_PROBE_STATUS="ready"
    REMOTE_PROBE_PATH="$probe"
    REMOTE_PROBE_OBJECTS="$probe_objects"
    return 0
  fi
  if [ -n "$current_sha" ]; then
    if git -C "$probe" merge-base --is-ancestor "$selected_sha" "$current_sha"; then
      result_tree="$(git -C "$probe" rev-parse "$current_sha^{tree}")"
    elif git -C "$probe" merge-base --is-ancestor "$current_sha" "$selected_sha"; then
      result_tree="$(git -C "$probe" rev-parse "$selected_sha^{tree}")"
    else
      result_tree="$(git -C "$probe" merge-tree --write-tree --no-messages "$current_sha" "$selected_sha" 2>/dev/null)" \
        || result_rc=$?
      if [ "$result_rc" -eq 1 ]; then
        REMOTE_PROBE_STATUS="merge_conflict"
        REMOTE_PROBE_ERROR_KIND="virtual_merge_conflict"
        REMOTE_PROBE_ERROR_DETAIL="remote probe merge-tree reported a conflict"
        plan_remote_probe_abort 2 || return $?
      fi
      if [ "$result_rc" -ne 0 ] || [ -z "$result_tree" ]; then
        REMOTE_PROBE_STATUS="probe_readback_failed"
        REMOTE_PROBE_ERROR_KIND="merge_tree_readback_failed"
        REMOTE_PROBE_ERROR_DETAIL="remote probe merge-tree did not produce a tree"
        plan_remote_probe_abort 1 || return $?
      fi
      result_tree="${result_tree%%$'\n'*}"
    fi
    REMOTE_PROBE_RESULT_TREE="$result_tree"
    if collision_path="$(GIT_ALTERNATE_OBJECT_DIRECTORIES="$probe_objects" \
      update_materialization_collision_path "$repo" "$current_sha" "$result_tree")"; then
      collision_rc=0
      REMOTE_PROBE_COLLISION_PATH="$collision_path"
    else
      collision_rc=$?
    fi
    if [ "$collision_rc" -eq 3 ]; then
      REMOTE_PROBE_STATUS="probe_readback_failed"
      REMOTE_PROBE_ERROR_KIND="materialization_collision_readback_failed"
      REMOTE_PROBE_ERROR_DETAIL="remote probe materialization collision readback failed"
      plan_remote_probe_abort 1 || return $?
    fi
    REMOTE_PROBE_HISTORY_STATE="$(GIT_ALTERNATE_OBJECT_DIRECTORIES="$probe_objects" \
      update_materialization_history_state "$repo" "$current_sha" "$selected_sha")"
  fi
  REMOTE_PROBE_STATUS="ready"
  REMOTE_PROBE_PATH="$probe"
  REMOTE_PROBE_OBJECTS="$probe_objects"
  return 0
}

plan_remote_probe_cleanup() {
  [ -n "$REMOTE_PROBE_PATH" ] || return 0
  if parent_remove_tree "$REMOTE_PROBE_PATH"; then
    REMOTE_PROBE_CLEANUP_STATUS="pass"
  else
    REMOTE_PROBE_CLEANUP_STATUS="failed"
    REMOTE_PROBE_STATUS="probe_cleanup_failed"
    REMOTE_PROBE_ERROR_KIND="probe_cleanup_failed"
    REMOTE_PROBE_ERROR_DETAIL="could not remove disposable probe '$REMOTE_PROBE_PATH'"
    return 1
  fi
  REMOTE_PROBE_PATH=""
  REMOTE_PROBE_OBJECTS=""
  if [ -n "$PLAN_REMOTE_ALTERNATES_PREVIOUS" ]; then
    export GIT_ALTERNATE_OBJECT_DIRECTORIES="$PLAN_REMOTE_ALTERNATES_PREVIOUS"
  else
    unset GIT_ALTERNATE_OBJECT_DIRECTORIES
  fi
  PLAN_REMOTE_ALTERNATES_PREVIOUS=""
  return 0
}

plan_remote_probe_abort() {
  local original_rc="$1"
  if [ -n "$REMOTE_PROBE_PATH" ]; then
    plan_remote_probe_cleanup || return 3
  fi
  return "$original_rc"
}

require_remote_branch_sha() {
  local remote="$1"
  local branch="$2"
  if ! resolve_remote_branch_sha "$remote" "$branch"; then
    die "${REMOTE_RESOLUTION_ERROR_DETAIL:-remote branch '$remote#$branch' could not be resolved}"
  fi
  printf '%s\n' "$REMOTE_RESOLUTION_SHA"
}

require_remote_commit_object() {
  local repo="$1"
  local remote="$2"
  local sha="$3"
  if ! ensure_remote_commit_object "$repo" "$remote" "$sha"; then
    die "${REMOTE_OBJECT_ERROR_DETAIL:-remote object '$sha' is not an available commit in '$repo'}"
  fi
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

submodule_stage0_gitlink_oid() {
  local mode=""
  local oid=""
  local stage=""
  local path=""
  local count=0

  SUBMODULE_STAGE0_STATUS="not_checked"
  SUBMODULE_STAGE0_MODE="<unavailable>"
  SUBMODULE_STAGE0_SHA=""
  SUBMODULE_STAGE0_STAGE="<unavailable>"
  SUBMODULE_STAGE0_PATH="<unavailable>"
  SUBMODULE_STAGE0_ERROR_KIND="none"
  SUBMODULE_STAGE0_ERROR_DETAIL=""
  while IFS=$' \t' read -r mode oid stage path; do
    [ -n "$path" ] || continue
    [ "$path" = "$PREFIX" ] || continue
    count=$((count + 1))
    SUBMODULE_STAGE0_MODE="$mode"
    SUBMODULE_STAGE0_SHA="$oid"
    SUBMODULE_STAGE0_STAGE="$stage"
    SUBMODULE_STAGE0_PATH="$path"
  done < <(git -C "$ROOT_DIR" ls-files --stage -- "$PREFIX" 2>/dev/null)

  if [ "$count" -ne 1 ]; then
    SUBMODULE_STAGE0_STATUS="invalid"
    SUBMODULE_STAGE0_ERROR_KIND="record_count"
    SUBMODULE_STAGE0_ERROR_DETAIL="expected exactly one stage-0 record for '$PREFIX', found $count"
    return 1
  fi
  if [ "$SUBMODULE_STAGE0_MODE" != "160000" ]; then
    SUBMODULE_STAGE0_STATUS="invalid"
    SUBMODULE_STAGE0_ERROR_KIND="mode"
    SUBMODULE_STAGE0_ERROR_DETAIL="stage-0 record for '$PREFIX' has mode '$SUBMODULE_STAGE0_MODE'"
    return 1
  fi
  if [ "$SUBMODULE_STAGE0_STAGE" != "0" ] || [ "$SUBMODULE_STAGE0_PATH" != "$PREFIX" ]; then
    SUBMODULE_STAGE0_STATUS="invalid"
    SUBMODULE_STAGE0_ERROR_KIND="stage_or_path"
    SUBMODULE_STAGE0_ERROR_DETAIL="stage-0 record for '$PREFIX' has stage '$SUBMODULE_STAGE0_STAGE' and path '$SUBMODULE_STAGE0_PATH'"
    return 1
  fi
  if ! [[ "$SUBMODULE_STAGE0_SHA" =~ ^[0-9a-fA-F]{40}([0-9a-fA-F]{24})?$ ]]; then
    SUBMODULE_STAGE0_STATUS="invalid"
    SUBMODULE_STAGE0_ERROR_KIND="object_id"
    SUBMODULE_STAGE0_ERROR_DETAIL="stage-0 record for '$PREFIX' has invalid object id '$SUBMODULE_STAGE0_SHA'"
    return 1
  fi
  SUBMODULE_STAGE0_STATUS="valid"
  return 0
}

submodule_parent_head_pin() {
  git -C "$ROOT_DIR" rev-parse "HEAD:$PREFIX" 2>/dev/null || true
}

submodule_main_worktree_collision_path() {
  local current_path=""
  local worktree_path=""
  local line=""
  local branch_ref=""
  local current_root=""

  current_root="$(git -C "$ROOT_DIR/$PREFIX" rev-parse --show-toplevel 2>/dev/null || true)"
  while IFS= read -r line; do
    case "$line" in
      worktree\ *)
        worktree_path="${line#worktree }"
        branch_ref=""
        ;;
      branch\ refs/heads/main)
        branch_ref="main"
        if [ "$worktree_path" != "$current_root" ]; then
          printf '%s\n' "$worktree_path"
          return 0
        fi
        ;;
    esac
  done < <(git -C "$ROOT_DIR/$PREFIX" worktree list --porcelain 2>/dev/null || true)
  return 1
}

submodule_main_ref_state() {
  local pin="$1"
  local main_sha=""
  main_sha="$(git -C "$ROOT_DIR/$PREFIX" rev-parse --verify refs/heads/main^{commit} 2>/dev/null || true)"
  if [ -z "$main_sha" ]; then
    printf '%s\n' absent
  elif [ "$main_sha" = "$pin" ]; then
    printf '%s\n' same
  elif git -C "$ROOT_DIR/$PREFIX" merge-base --is-ancestor "$main_sha" "$pin"; then
    printf '%s\n' ancestor
  elif git -C "$ROOT_DIR/$PREFIX" merge-base --is-ancestor "$pin" "$main_sha"; then
    printf '%s\n' descendant
  else
    printf '%s\n' divergent
  fi
}

is_submodule_prefix() {
  [ "$(prefix_git_mode)" = "160000" ] \
    || [ "$(prefix_index_mode)" = "160000" ]
}

submodule_checkout_initialized() {
  [ -e "$ROOT_DIR/$PREFIX/.git" ] \
    && git -C "$ROOT_DIR/$PREFIX" rev-parse --is-inside-work-tree >/dev/null 2>&1
}

submodule_unresolved_merge_conflict() {
  [ -n "$(git -C "$ROOT_DIR" ls-files --unmerged -- "$PREFIX")" ] \
    || update_materialization_unresolved_conflict "$ROOT_DIR/$PREFIX"
}

submodule_materialization_result_tree() {
  local current_sha="$1"
  local remote_sha="$2"
  update_materialization_result_tree "$ROOT_DIR/$PREFIX" "$current_sha" "$remote_sha"
}

submodule_materialization_collision_path() {
  local current_sha="$1"
  local result_tree="$2"
  update_materialization_collision_path "$ROOT_DIR/$PREFIX" "$current_sha" "$result_tree"
}

submodule_history_state() {
  local current_sha="$1"
  local remote_sha="$2"
  update_materialization_history_state "$ROOT_DIR/$PREFIX" "$current_sha" "$remote_sha"
}

materialize_submodule_remote_branch() {
  local current_sha="$1"
  local remote_sha="$2"
  local remote_branch="$3"
  local result_tree="${4:-}"
  local collision_path=""
  local collision_rc=0
  local merge_log=""
  local result_tree_rc=0

  if submodule_unresolved_merge_conflict; then
    echo "agent_canon_materialization_unresolved_merge_conflict=yes"
    echo "agent_canon_materialization_merge_conflict=yes"
    echo "agent_canon_materialization_conflict_type=existing_unresolved_index"
    echo "agent_canon_materialization_result=blocked_unresolved_merge_conflict"
    return 2
  fi
  if [ -z "$result_tree" ]; then
    result_tree="$(submodule_materialization_result_tree "$current_sha" "$remote_sha")" \
      || result_tree_rc=$?
    if [ "$result_tree_rc" -eq 2 ]; then
      echo "agent_canon_materialization_unresolved_merge_conflict=no"
      echo "agent_canon_materialization_merge_conflict=yes"
      echo "agent_canon_materialization_conflict_type=virtual_merge_result"
      echo "agent_canon_materialization_result=blocked_merge_conflict"
      return 2
    fi
    [ "$result_tree_rc" -eq 0 ] || return "$result_tree_rc"
  fi
  echo "agent_canon_materialization_unresolved_merge_conflict=no"
  echo "agent_canon_materialization_merge_conflict=no"
  echo "agent_canon_materialization_conflict_type=none"
  collision_path="$(submodule_materialization_collision_path "$current_sha" "$result_tree")" \
    || collision_rc=$?
  if [ "$collision_rc" -eq 0 ]; then
    echo "agent_canon_materialization_collision=yes"
    printf 'agent_canon_materialization_collision_path=%q\n' "$collision_path"
    echo "agent_canon_materialization_result=blocked_unpreservable_collision"
    return 2
  fi
  [ "$collision_rc" -eq 1 ] || return "$collision_rc"

  echo "agent_canon_materialization_collision=no"
  if git -C "$ROOT_DIR/$PREFIX" merge-base --is-ancestor "$remote_sha" "$current_sha"; then
    echo "agent_canon_materialization_result=already_contains_remote"
    return 0
  fi

  merge_log_dir="$(parent_temp_dir "$CANON_PARENT_TMPDIR" merge-log)"
  merge_log="$merge_log_dir/output"
  local merge_output=""
  if merge_output="$(git -C "$ROOT_DIR/$PREFIX" merge --no-autostash --no-edit "origin/$remote_branch" 2>&1)"; then
    parent_write_file "$merge_log" "$merge_output"
    cat "$merge_log"
    parent_remove_file "$merge_log"
    echo "agent_canon_materialization_result=merged_remote"
    return 0
  fi

  parent_write_file "$merge_log" "$merge_output"
  cat "$merge_log" >&2
  parent_remove_file "$merge_log"
  if submodule_unresolved_merge_conflict; then
    echo "agent_canon_materialization_unresolved_merge_conflict=yes"
    echo "agent_canon_materialization_result=blocked_unresolved_merge_conflict"
    return 2
  fi
  echo "agent_canon_materialization_result=failed_without_conflict"
  return 1
}

attach_transaction_capture() {
  local repo="$1"
  local git_dir=""
  local objects_dir=""
  local fetch_head=""
  local config_rc=0
  local command_rc=0

  ATTACH_TXN_RESTORE_STATUS="not_attempted"
  ATTACH_TXN_RESTORE_ERROR_KIND="none"
  ATTACH_TXN_RESTORE_ERROR_DETAIL=""
  ATTACH_TXN_CLEANUP_STATUS="not_attempted"
  ATTACH_TXN_CLEANUP_ERROR_DETAIL=""
  if ! ATTACH_TXN_DIR="$(parent_temp_dir "$CANON_PARENT_TMPDIR" attach-transaction)"; then
    return 1
  fi
  if ! git_dir="$(git -C "$repo" rev-parse --git-dir 2>/dev/null)"; then
    return 1
  fi
  [ -n "$git_dir" ] || return 1
  if [[ "$git_dir" != /* ]]; then
    git_dir="$repo/$git_dir"
  fi
  if ! ATTACH_TXN_GIT_DIR="$(realpath -m -- "$git_dir")"; then
    return 1
  fi
  [ -n "$ATTACH_TXN_GIT_DIR" ] || return 1
  if ! objects_dir="$(git -C "$repo" rev-parse --git-path objects 2>/dev/null)"; then
    return 1
  fi
  [ -n "$objects_dir" ] || return 1
  if [[ "$objects_dir" != /* ]]; then
    objects_dir="$repo/$objects_dir"
  fi
  if ! ATTACH_TXN_OBJECTS_DIR="$(realpath -m -- "$objects_dir")"; then
    return 1
  fi
  [ -n "$ATTACH_TXN_OBJECTS_DIR" ] || return 1
  if ! fetch_head="$(git -C "$repo" rev-parse --git-path FETCH_HEAD 2>/dev/null)"; then
    return 1
  fi
  [ -n "$fetch_head" ] || return 1
  if [[ "$fetch_head" != /* ]]; then
    fetch_head="$repo/$fetch_head"
  fi
  if ! ATTACH_TXN_FETCH_HEAD_PATH="$(realpath -m -- "$fetch_head")"; then
    return 1
  fi
  [ -n "$ATTACH_TXN_FETCH_HEAD_PATH" ] || return 1
  if ! ATTACH_TXN_BEFORE_HEAD="$(git -C "$repo" rev-parse HEAD 2>/dev/null)"; then
    return 1
  fi
  [ -n "$ATTACH_TXN_BEFORE_HEAD" ] || return 1
  if ATTACH_TXN_BEFORE_MAIN_SHA="$(git -C "$repo" rev-parse --verify refs/heads/main 2>/dev/null)"; then
    :
  else
    command_rc=$?
    [ "$command_rc" -eq 128 ] || return 1
    ATTACH_TXN_BEFORE_MAIN_SHA=""
  fi
  if ATTACH_TXN_BEFORE_ORIGIN_SHA="$(git -C "$repo" rev-parse --verify refs/remotes/origin/main 2>/dev/null)"; then
    :
  else
    command_rc=$?
    [ "$command_rc" -eq 128 ] || return 1
    ATTACH_TXN_BEFORE_ORIGIN_SHA=""
  fi
  if ! ATTACH_TXN_BEFORE_STATUS="$(git -C "$repo" status --porcelain=v1 --untracked-files=all 2>/dev/null)"; then
    return 1
  fi
  if [ -e "$ATTACH_TXN_FETCH_HEAD_PATH" ]; then
    ATTACH_TXN_BEFORE_FETCH_EXISTS="yes"
    if ! parent_copy_file "$ATTACH_TXN_FETCH_HEAD_PATH" "$ATTACH_TXN_DIR/fetch-head.before" \
      "agent-canon-attach-capture"; then
      return 1
    fi
  else
    ATTACH_TXN_BEFORE_FETCH_EXISTS="no"
  fi
  if ! parent_capture_subprocess "$ATTACH_TXN_DIR/worktrees.before" \
    "agent-canon-attach-capture" git -C "$repo" worktree list --porcelain; then
    return 1
  fi
  if parent_capture_subprocess "$ATTACH_TXN_DIR/branch-main.before" \
    "agent-canon-attach-capture" git -C "$repo" config --local --null --get-regexp '^branch\.main\.'; then
    config_rc=0
  else
    config_rc=$?
  fi
  if [ "$config_rc" -eq 1 ]; then
    if ! parent_write_file "$ATTACH_TXN_DIR/branch-main.before" "" \
      "agent-canon-attach-capture"; then
      return 1
    fi
  elif [ "$config_rc" -ne 0 ]; then
    return 1
  fi
  if ! parent_capture_subprocess "$ATTACH_TXN_DIR/objects.before" \
    "agent-canon-attach-capture" \
    bash -c 'set -o pipefail; find "$1" -type f -printf "%P\\n" 2>/dev/null | LC_ALL=C sort' \
    _ "$ATTACH_TXN_OBJECTS_DIR"; then
    return 1
  fi
  if ! parent_capture_subprocess "$ATTACH_TXN_DIR/objects.before.sha256" \
    "agent-canon-attach-capture" \
    bash -c 'while IFS= read -r rel; do sha256sum "$1/$rel" || exit 1; done <"$2"' \
    _ "$ATTACH_TXN_OBJECTS_DIR" "$ATTACH_TXN_DIR/objects.before"; then
    return 1
  fi
  if [ "${AGENT_CANON_ATTACH_FAIL_PHASE:-}" = "capture" ]; then
    return 1
  fi
}

attach_transaction_restore_ref() {
  local repo="$1"
  local ref="$2"
  local before_sha="$3"
  local current_sha=""

  current_sha="$(git -C "$repo" rev-parse --verify "$ref" 2>/dev/null || true)"
  if [ -n "$before_sha" ]; then
    [ -n "$current_sha" ] || return 1
    git -C "$repo" update-ref "$ref" "$before_sha" "$current_sha"
  elif [ -n "$current_sha" ]; then
    git -C "$repo" update-ref -d "$ref" "$current_sha"
  fi
}

attach_transaction_restore_config() {
  local repo="$1"
  local record=""
  local key=""
  local value=""
  local config_rc=0

  git -C "$repo" config --local --get-regexp '^branch\.main\.' >/dev/null 2>&1 \
    || config_rc=$?
  if [ "$config_rc" -eq 0 ]; then
    git -C "$repo" config --local --remove-section branch.main >/dev/null 2>&1 \
      || return 1
  elif [ "$config_rc" -ne 1 ]; then
    return 1
  fi
  while IFS= read -r -d '' record; do
    key="${record%%$'\n'*}"
    value="${record#*$'\n'}"
    [ -n "$key" ] || continue
    git -C "$repo" config --local --add "$key" "$value" || return 1
  done <"$ATTACH_TXN_DIR/branch-main.before"
}

attach_transaction_remove_new_objects() {
  local rel=""
  while IFS= read -r rel; do
    [ -n "$rel" ] || continue
    if ! grep -Fqx -- "$rel" "$ATTACH_TXN_DIR/objects.before"; then
      parent_remove_file "$ATTACH_TXN_OBJECTS_DIR/$rel" || return 1
    fi
  done < <(find "$ATTACH_TXN_OBJECTS_DIR" -type f -printf '%P\n' 2>/dev/null | LC_ALL=C sort)
}

attach_transaction_capture_current_object_state() {
  local target="$1"
  find "$ATTACH_TXN_OBJECTS_DIR" -type f -printf '%P\n' 2>/dev/null \
    | LC_ALL=C sort >"$ATTACH_TXN_DIR/objects.after"
  while IFS= read -r rel; do
    sha256sum "$ATTACH_TXN_OBJECTS_DIR/$rel"
  done <"$ATTACH_TXN_DIR/objects.after" >"$target"
}

attach_transaction_config_state_matches() {
  local repo="$1"
  local config_rc=0
  git -C "$repo" config --local --null --get-regexp '^branch\.main\.' \
    >"$ATTACH_TXN_DIR/branch-main.after" 2>/dev/null || config_rc=$?
  if [ "$config_rc" -eq 1 ]; then
    : >"$ATTACH_TXN_DIR/branch-main.after"
  elif [ "$config_rc" -ne 0 ]; then
    return 1
  fi
  cmp -s "$ATTACH_TXN_DIR/branch-main.before" "$ATTACH_TXN_DIR/branch-main.after"
}

attach_transaction_restore() {
  local repo="$1"
  local current_head=""
  local current_status=""
  local current_fetch_digest=""
  local before_fetch_digest=""
  local current_worktrees=""
  local before_worktrees=""
  local rollback_ok=0

  ATTACH_TXN_RESTORE_STATUS="in_progress"
  ATTACH_TXN_RESTORE_ERROR_KIND="none"
  ATTACH_TXN_RESTORE_ERROR_DETAIL=""
  if [ -z "$ATTACH_TXN_DIR" ] || [ ! -d "$ATTACH_TXN_DIR" ]; then
    ATTACH_TXN_RESTORE_STATUS="failed"
    ATTACH_TXN_RESTORE_ERROR_KIND="transaction_evidence_missing"
    ATTACH_TXN_RESTORE_ERROR_DETAIL="attach transaction evidence directory is unavailable"
    echo "agent_canon_attach_rollback=fail"
    echo "agent_canon_attach_rollback_error_kind=$ATTACH_TXN_RESTORE_ERROR_KIND"
    printf 'agent_canon_attach_rollback_error_detail=%q\n' "$ATTACH_TXN_RESTORE_ERROR_DETAIL"
    return 1
  fi
  if [ "${AGENT_CANON_ATTACH_FAIL_ROLLBACK:-}" = "1" ]; then
    ATTACH_TXN_RESTORE_STATUS="failed"
    ATTACH_TXN_RESTORE_ERROR_KIND="injected_failure"
    ATTACH_TXN_RESTORE_ERROR_DETAIL="rollback failure was injected for transaction testing"
    echo "agent_canon_attach_rollback=fail"
    echo "agent_canon_attach_rollback_error_kind=$ATTACH_TXN_RESTORE_ERROR_KIND"
    printf 'agent_canon_attach_rollback_error_detail=%q\n' "$ATTACH_TXN_RESTORE_ERROR_DETAIL"
    printf 'agent_canon_attach_transaction_dir=%q\n' "$ATTACH_TXN_DIR"
    return 1
  fi

  git -C "$repo" switch --detach "$ATTACH_TXN_BEFORE_HEAD" >/dev/null 2>&1 || rollback_ok=1
  attach_transaction_restore_ref "$repo" refs/heads/main "$ATTACH_TXN_BEFORE_MAIN_SHA" || rollback_ok=1
  attach_transaction_restore_ref "$repo" refs/remotes/origin/main "$ATTACH_TXN_BEFORE_ORIGIN_SHA" || rollback_ok=1
  attach_transaction_restore_config "$repo" || rollback_ok=1
  if [ "$ATTACH_TXN_BEFORE_FETCH_EXISTS" = "yes" ]; then
    parent_copy_file "$ATTACH_TXN_DIR/fetch-head.before" "$ATTACH_TXN_FETCH_HEAD_PATH" \
      "agent-canon-attach-rollback" || rollback_ok=1
  elif [ -e "$ATTACH_TXN_FETCH_HEAD_PATH" ]; then
    parent_remove_file "$ATTACH_TXN_FETCH_HEAD_PATH" "agent-canon-attach-rollback" || rollback_ok=1
  fi
  attach_transaction_remove_new_objects || rollback_ok=1
  attach_transaction_capture_current_object_state "$ATTACH_TXN_DIR/objects.after.sha256" || rollback_ok=1
  current_head="$(git -C "$repo" rev-parse HEAD 2>/dev/null || true)"
  current_status="$(git -C "$repo" status --porcelain=v1 --untracked-files=all)"
  current_worktrees="$(git -C "$repo" worktree list --porcelain)"
  if [ -f "$ATTACH_TXN_DIR/worktrees.before" ]; then
    before_worktrees="$(cat "$ATTACH_TXN_DIR/worktrees.before")" || rollback_ok=1
  else
    rollback_ok=1
  fi
  if [ "$current_head" != "$ATTACH_TXN_BEFORE_HEAD" ] \
    || [ "$current_status" != "$ATTACH_TXN_BEFORE_STATUS" ] \
    || [ "$(git -C "$repo" rev-parse --verify refs/heads/main 2>/dev/null || true)" != "$ATTACH_TXN_BEFORE_MAIN_SHA" ] \
    || [ "$(git -C "$repo" rev-parse --verify refs/remotes/origin/main 2>/dev/null || true)" != "$ATTACH_TXN_BEFORE_ORIGIN_SHA" ] \
    || [ "$current_worktrees" != "$before_worktrees" ]; then
    rollback_ok=1
  fi
  if ! cmp -s "$ATTACH_TXN_DIR/objects.before" "$ATTACH_TXN_DIR/objects.after" \
    || ! cmp -s "$ATTACH_TXN_DIR/objects.before.sha256" "$ATTACH_TXN_DIR/objects.after.sha256"; then
    rollback_ok=1
  fi
  attach_transaction_config_state_matches "$repo" || rollback_ok=1
  if [ "$ATTACH_TXN_BEFORE_FETCH_EXISTS" = "yes" ]; then
    current_fetch_digest="$(sha256sum "$ATTACH_TXN_FETCH_HEAD_PATH" 2>/dev/null || true)"
    before_fetch_digest="$(sha256sum "$ATTACH_TXN_DIR/fetch-head.before" 2>/dev/null || true)"
    [ "$current_fetch_digest" = "$before_fetch_digest" ] || rollback_ok=1
  else
    [ ! -e "$ATTACH_TXN_FETCH_HEAD_PATH" ] || rollback_ok=1
  fi
  if [ "$rollback_ok" -eq 0 ]; then
    ATTACH_TXN_RESTORE_STATUS="pass"
    echo "agent_canon_attach_rollback=pass"
    return 0
  fi
  ATTACH_TXN_RESTORE_STATUS="failed"
  ATTACH_TXN_RESTORE_ERROR_KIND="state_readback_mismatch"
  ATTACH_TXN_RESTORE_ERROR_DETAIL="attach rollback did not restore the captured source state"
  echo "agent_canon_attach_rollback=fail"
  echo "agent_canon_attach_rollback_error_kind=$ATTACH_TXN_RESTORE_ERROR_KIND"
  printf 'agent_canon_attach_rollback_error_detail=%q\n' "$ATTACH_TXN_RESTORE_ERROR_DETAIL"
  printf 'agent_canon_attach_transaction_dir=%q\n' "$ATTACH_TXN_DIR"
  return 1
}

attach_transaction_cleanup() {
  [ -n "$ATTACH_TXN_DIR" ] || return 0
  ATTACH_TXN_CLEANUP_STATUS="in_progress"
  ATTACH_TXN_CLEANUP_ERROR_DETAIL=""
  if ! parent_remove_tree "$ATTACH_TXN_DIR" 2>/dev/null; then
    ATTACH_TXN_CLEANUP_STATUS="failed"
    ATTACH_TXN_CLEANUP_ERROR_DETAIL="could not remove attach transaction evidence"
    echo "agent_canon_attach_transaction_cleanup=fail"
    printf 'agent_canon_attach_transaction_cleanup_detail=%q\n' "$ATTACH_TXN_CLEANUP_ERROR_DETAIL"
    printf 'agent_canon_attach_transaction_dir=%q\n' "$ATTACH_TXN_DIR"
    return 1
  fi
  ATTACH_TXN_CLEANUP_STATUS="pass"
  ATTACH_TXN_DIR=""
  echo "agent_canon_attach_transaction_cleanup=pass"
  return 0
}

attach_transaction_abort() {
  local repo="$1"
  local result="$2"
  local return_rc="${3:-2}"

  if ! attach_transaction_restore "$repo"; then
    echo "agent_canon_attach_result=blocked_rollback_failed"
    printf 'agent_canon_attach_transaction_dir=%q\n' "$ATTACH_TXN_DIR"
    return 3
  fi
  if ! attach_transaction_cleanup; then
    echo "agent_canon_attach_result=blocked_transaction_cleanup_failed"
    return 3
  fi
  echo "agent_canon_attach_result=$result"
  return "$return_rc"
}

submodule_commit() {
  git -C "$ROOT_DIR" rev-parse "HEAD:$PREFIX"
}

attach_submodule_main_to_staged_pin() {
  local pin="$1"
  local remote_url="$2"
  local remote_sha="${3:-}"
  local current_branch=""
  local worktree_head=""
  local main_state=""
  local collision_path=""
  local origin_sha=""
  local fetch_output=""
  local upstream=""
  local stage_oid=""

  if ! submodule_stage0_gitlink_oid; then
    echo "agent_canon_attach_stage0_status=$SUBMODULE_STAGE0_STATUS"
    echo "agent_canon_attach_stage0_error_kind=$SUBMODULE_STAGE0_ERROR_KIND"
    printf 'agent_canon_attach_stage0_error_detail=%q\n' "$SUBMODULE_STAGE0_ERROR_DETAIL"
    return 2
  fi
  stage_oid="$SUBMODULE_STAGE0_SHA"
  if [ "$stage_oid" != "$pin" ]; then
    echo "agent_canon_attach_stage0_status=mismatch"
    echo "agent_canon_attach_stage0_oid=$stage_oid"
    echo "agent_canon_attach_expected_pin=$pin"
    return 2
  fi
  current_branch="$(git -C "$ROOT_DIR/$PREFIX" symbolic-ref --quiet --short HEAD 2>/dev/null || true)"
  worktree_head="$(git -C "$ROOT_DIR/$PREFIX" rev-parse HEAD 2>/dev/null || true)"
  if [ -n "$(git -C "$ROOT_DIR/$PREFIX" status --short --untracked-files=all)" ]; then
    echo "agent_canon_attach_result=blocked_dirty"
    return 2
  fi
  if [ -n "$current_branch" ] || [ "$worktree_head" != "$pin" ]; then
    echo "agent_canon_attach_result=blocked_nonpin"
    echo "agent_canon_attach_branch=${current_branch:-<detached>}"
    echo "agent_canon_attach_worktree_head=${worktree_head:-<unavailable>}"
    return 2
  fi
  main_state="$(submodule_main_ref_state "$pin")"
  collision_path="$(submodule_main_worktree_collision_path || true)"
  if [ -n "$collision_path" ]; then
    echo "agent_canon_attach_result=blocked_main_worktree_collision"
    printf 'agent_canon_attach_main_worktree_collision_path=%q\n' "$collision_path"
    return 2
  fi
  case "$main_state" in
    absent|same|ancestor) ;;
    descendant|divergent)
      echo "agent_canon_attach_result=blocked_main_ref_$main_state"
      echo "agent_canon_attach_main_ref_state=$main_state"
      return 2
      ;;
    *)
      echo "agent_canon_attach_result=blocked_main_ref_invalid"
      return 2
      ;;
  esac
  if [ -z "$remote_url" ]; then
    echo "agent_canon_attach_result=blocked_remote_resolution"
    return 2
  fi
  if ! resolve_remote_branch_sha "$remote_url" "$DEFAULT_BRANCH"; then
    echo "agent_canon_attach_result=blocked_remote_resolution"
    echo "agent_canon_attach_remote_resolution_status=$REMOTE_RESOLUTION_STATUS"
    echo "agent_canon_attach_remote_resolution_error_kind=$REMOTE_RESOLUTION_ERROR_KIND"
    printf 'agent_canon_attach_remote_resolution_error_detail=%q\n' "$REMOTE_RESOLUTION_ERROR_DETAIL"
    return 2
  fi
  remote_sha="$REMOTE_RESOLUTION_SHA"
  if ! [[ "$remote_sha" =~ ^[0-9a-fA-F]{40}([0-9a-fA-F]{24})?$ ]]; then
    echo "agent_canon_attach_result=blocked_remote_resolution"
    return 2
  fi
  if ! attach_transaction_capture "$ROOT_DIR/$PREFIX"; then
    echo "agent_canon_attach_result=blocked_transaction_capture_failed"
    if [ -n "$ATTACH_TXN_DIR" ]; then
      if ! attach_transaction_cleanup; then
        echo "agent_canon_attach_result=blocked_transaction_cleanup_failed"
        return 3
      fi
    fi
    return 3
  fi
  REMOTE_TRACKING_STATUS="not_attempted"
  REMOTE_TRACKING_ERROR_KIND="none"
  REMOTE_TRACKING_ERROR_DETAIL=""
  REMOTE_TRACKING_EXPECTED_SHA="$remote_sha"
  REMOTE_TRACKING_FETCHED_SHA=""
  REMOTE_TRACKING_URL="$remote_url"
  REMOTE_TRACKING_BRANCH="$DEFAULT_BRANCH"
  if ! fetch_output="$(git -C "$ROOT_DIR/$PREFIX" fetch --no-write-fetch-head origin \
    "refs/heads/$DEFAULT_BRANCH:refs/remotes/origin/$DEFAULT_BRANCH" 2>&1)"; then
    REMOTE_TRACKING_STATUS="fetch_failed"
    REMOTE_TRACKING_ERROR_KIND="tracking_fetch_failed"
    REMOTE_TRACKING_ERROR_DETAIL="$fetch_output"
    attach_transaction_abort "$ROOT_DIR/$PREFIX" blocked_origin_main_fetch || return $?
  fi
  origin_sha="$(git -C "$ROOT_DIR/$PREFIX" rev-parse --verify "refs/remotes/origin/$DEFAULT_BRANCH^{commit}" 2>/dev/null || true)"
  REMOTE_TRACKING_FETCHED_SHA="$origin_sha"
  if [ "$origin_sha" != "$remote_sha" ]; then
    REMOTE_TRACKING_STATUS="mismatch"
    REMOTE_TRACKING_ERROR_KIND="tracking_sha_mismatch"
    REMOTE_TRACKING_ERROR_DETAIL="origin/$DEFAULT_BRANCH '${origin_sha:-<unavailable>}' does not match expected '$remote_sha'"
    attach_transaction_abort "$ROOT_DIR/$PREFIX" blocked_origin_main_mismatch || return $?
  fi
  REMOTE_TRACKING_STATUS="matched"

  case "$main_state" in
    absent)
      git -C "$ROOT_DIR/$PREFIX" branch main "$pin"
      ;;
    same)
      git -C "$ROOT_DIR/$PREFIX" switch main
      ;;
    ancestor)
      git -C "$ROOT_DIR/$PREFIX" switch main
      git -C "$ROOT_DIR/$PREFIX" merge --no-autostash --ff-only "$pin"
      ;;
  esac
  if [ "${AGENT_CANON_ATTACH_FAIL_PHASE:-}" = "upstream" ]; then
    attach_transaction_abort "$ROOT_DIR/$PREFIX" blocked_injected_upstream_failure || return $?
  fi
  git -C "$ROOT_DIR/$PREFIX" branch --set-upstream-to="origin/$DEFAULT_BRANCH" main >/dev/null
  current_branch="$(git -C "$ROOT_DIR/$PREFIX" symbolic-ref --quiet --short HEAD 2>/dev/null || true)"
  worktree_head="$(git -C "$ROOT_DIR/$PREFIX" rev-parse HEAD 2>/dev/null || true)"
  upstream="$(git -C "$ROOT_DIR/$PREFIX" for-each-ref --format='%(upstream:short)' refs/heads/main 2>/dev/null || true)"
  if [ "$current_branch" != "main" ] || [ "$worktree_head" != "$pin" ] \
    || [ -n "$(git -C "$ROOT_DIR/$PREFIX" status --short --untracked-files=all)" ] \
    || [ "$upstream" != "origin/main" ]; then
    echo "agent_canon_attach_result=blocked_readback"
    echo "agent_canon_attach_branch=${current_branch:-<detached>}"
    echo "agent_canon_attach_head=${worktree_head:-<unavailable>}"
    echo "agent_canon_attach_upstream=${upstream:-<unset>}"
    attach_transaction_abort "$ROOT_DIR/$PREFIX" blocked_readback || return $?
  fi
  if [ "${AGENT_CANON_ATTACH_FAIL_PHASE:-}" = "readback" ]; then
    attach_transaction_abort "$ROOT_DIR/$PREFIX" blocked_injected_readback_failure || return $?
  fi
  if ! attach_transaction_cleanup; then
    echo "agent_canon_attach_result=blocked_transaction_cleanup_failed"
    return 3
  fi
  echo "agent_canon_attach_result=attached"
  echo "agent_canon_attach_main_ref_state=$main_state"
  echo "agent_canon_attach_head=$worktree_head"
  echo "agent_canon_attach_upstream=$upstream"
  return 0
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
        parent_remove_file "$path"
        repo_local_goal_template | python3 "${SCRIPT_DIR}/agent_tools/parent_root_side_effects.py" \
          write --root "$PARENT_ROOT_DIR" --candidate "$path" --purpose agent-canon-sync >/dev/null
        echo "goal_md=converted_from_shared_symlink"
        ;;
    esac
  elif [ ! -e "$path" ]; then
    repo_local_goal_template | python3 "${SCRIPT_DIR}/agent_tools/parent_root_side_effects.py" \
      write --root "$PARENT_ROOT_DIR" --candidate "$path" --purpose agent-canon-sync >/dev/null
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

build_update_transition_specs() {
  python3 "$ROOT_DIR/$PREFIX/tools/agent_tools/surface_manifest.py" \
    --root "$ROOT_DIR" --prefix "$PREFIX" --manifest "$SURFACE_MANIFEST" update-transition-specs
}

require_live_surface_selection() {
  if ! build_link_specs >/dev/null; then
    die "surface sync requires live-agent-canon,false,explicit-opt-in selection"
  fi
}

active_root_copy_transition_id() {
  local previous_pin=""
  local staged_pin=""
  local source_pin=""
  local transition_id=""
  local from_agent_canon_pins=""
  local unused=""

  is_submodule_prefix || return 1
  previous_pin="$(git -C "$ROOT_DIR" rev-parse "HEAD:$PREFIX" 2>/dev/null || true)"
  staged_pin="$(git -C "$ROOT_DIR" rev-parse ":$PREFIX" 2>/dev/null || true)"
  source_pin="$(git -C "$ROOT_DIR/$PREFIX" rev-parse HEAD 2>/dev/null || true)"
  [ -n "$previous_pin" ] && [ -n "$staged_pin" ] && [ -n "$source_pin" ] || return 1
  [ "$staged_pin" = "$source_pin" ] && [ "$previous_pin" != "$source_pin" ] || return 1

  while IFS="$(printf '\t')" read -r transition_id from_agent_canon_pins unused; do
    [ -n "$transition_id" ] || continue
    case ",$from_agent_canon_pins," in
      *",$previous_pin,"*)
        printf '%s\n' "$transition_id"
        return 0
        ;;
    esac
  done < <(build_update_transition_specs)
  return 1
}

root_copy_transition_identity_matches() {
  local path="$1"
  local transition_id="$2"
  local abs_path="$ROOT_DIR/$path"
  local actual_blob=""
  local actual_sha256=""
  local actual_mode=""
  local actual_target=""
  local spec_transition_id=""
  local from_agent_canon_pins=""
  local spec_path=""
  local kind=""
  local git_blob=""
  local content_sha256=""
  local git_mode=""
  local symlink_target=""

  actual_mode="$(git -C "$ROOT_DIR" ls-files -s -- "$path" | awk 'NR == 1 {print $1}')"
  if [ -L "$abs_path" ]; then
    actual_target="$(readlink "$abs_path")"
    actual_blob="$(printf '%s' "$actual_target" | git -C "$ROOT_DIR" hash-object --stdin)"
    actual_sha256="$(printf '%s' "$actual_target" | sha256sum | awk '{print $1}')"
  elif [ -f "$abs_path" ]; then
    actual_blob="$(git -C "$ROOT_DIR" hash-object --no-filters "$abs_path")"
    actual_sha256="$(sha256sum "$abs_path" | awk '{print $1}')"
  else
    return 1
  fi

  while IFS="$(printf '\t')" read -r \
    spec_transition_id from_agent_canon_pins spec_path kind git_blob \
    content_sha256 git_mode symlink_target; do
    [ "$spec_transition_id" = "$transition_id" ] || continue
    [ "$spec_path" = "$path" ] || continue
    [ "$actual_blob" = "$git_blob" ] || continue
    [ "$actual_sha256" = "$content_sha256" ] || continue
    [ "$actual_mode" = "$git_mode" ] || continue
    if [ "$kind" = "regular" ] && [ -f "$abs_path" ] && [ ! -L "$abs_path" ]; then
      return 0
    fi
    if [ "$kind" = "symlink" ] && [ -L "$abs_path" ] \
      && [ "$actual_target" = "$symlink_target" ]; then
      return 0
    fi
  done < <(build_update_transition_specs)
  return 1
}

preflight_root_copy_transition() {
  local specs=""
  local path=""

  ACTIVE_ROOT_COPY_TRANSITION_ID="$(active_root_copy_transition_id || true)"
  ROOT_COPY_TRANSITION_CANDIDATES=()
  ROOT_COPY_TRANSITION_REMOVED_PATHS=()
  [ -n "$ACTIVE_ROOT_COPY_TRANSITION_ID" ] || return 0
  specs="$(build_update_transition_specs)"
  while IFS= read -r path; do
    [ -n "$path" ] || continue
    if [ ! -e "$ROOT_DIR/$path" ] && [ ! -L "$ROOT_DIR/$path" ]; then
      continue
    fi
    if root_copy_transition_identity_matches "$path" "$ACTIVE_ROOT_COPY_TRANSITION_ID"; then
      ROOT_COPY_TRANSITION_CANDIDATES+=("$path")
      echo "update_transition[$ACTIVE_ROOT_COPY_TRANSITION_ID][$path]=known_legacy_identity"
    else
      echo "update_transition[$ACTIVE_ROOT_COPY_TRANSITION_ID][$path]=parent_owned_preserved"
    fi
  done < <(
    printf '%s\n' "$specs" \
      | awk -F "$(printf '\t')" -v transition="$ACTIVE_ROOT_COPY_TRANSITION_ID" \
          '$1 == transition {print $3}' \
      | sort -u
  )
}

migrate_root_copy_transition() {
  local transition_state_dir="$ROOT_DIR/.agent-canon/update-lifecycle"
  local quarantine=""
  local path=""
  local moved_path=""
  local index=0
  local -a moved_paths=()

  [ -n "$ACTIVE_ROOT_COPY_TRANSITION_ID" ] || return 0
  [ "${#ROOT_COPY_TRANSITION_CANDIDATES[@]}" -gt 0 ] || return 0

  # Revalidate every candidate before moving the first path. Diverged paths
  # were already classified as parent-owned and are not part of this set.
  for path in "${ROOT_COPY_TRANSITION_CANDIDATES[@]}"; do
    root_copy_transition_identity_matches "$path" "$ACTIVE_ROOT_COPY_TRANSITION_ID" \
      || die "update transition candidate changed after preflight: $path"
  done

  parent_ensure_dir "$transition_state_dir"
  quarantine="$(parent_temp_dir "$transition_state_dir" root-surface-transition)"
  case "$quarantine" in
    "$transition_state_dir"/root-surface-transition.*) ;;
    *) die "invalid root-surface transition quarantine path" ;;
  esac

  for path in "${ROOT_COPY_TRANSITION_CANDIDATES[@]}"; do
    parent_ensure_dir "$quarantine/$(dirname "$path")"
    if ! parent_move_path "$ROOT_DIR/$path" "$quarantine/$path"; then
      for ((index = ${#moved_paths[@]} - 1; index >= 0; index--)); do
        moved_path="${moved_paths[$index]}"
        parent_ensure_dir "$ROOT_DIR/$(dirname "$moved_path")"
        parent_move_path "$quarantine/$moved_path" "$ROOT_DIR/$moved_path" \
          || die "update transition rollback failed for $moved_path"
      done
      parent_remove_tree "$quarantine"
      die "update transition move failed for $path; all earlier moves were restored"
    fi
    moved_paths+=("$path")
  done

  parent_remove_tree "$quarantine"
  for path in "${ROOT_COPY_TRANSITION_CANDIDATES[@]}"; do
    ROOT_COPY_TRANSITION_REMOVED_PATHS+=("$path")
    echo "update_transition[$ACTIVE_ROOT_COPY_TRANSITION_ID][$path]=removed_known_legacy_identity"
    parent_remove_empty_dir "$ROOT_DIR/$(dirname "$path")" || true
  done
}

link_path() {
  local path="$1"
  local target="$2"
  local abs_path="$ROOT_DIR/$path"
  if [ -d "$abs_path" ] && [ ! -L "$abs_path" ]; then
    parent_remove_tree "$abs_path"
  elif [ -e "$abs_path" ] || [ -L "$abs_path" ]; then
    parent_remove_file "$abs_path"
  fi
  parent_ensure_dir "$(dirname "$abs_path")"
  parent_symlink "$target" "$abs_path"
}

copy_path() {
  local path="$1"
  local source="$2"
  [ -n "$path" ] || die "copy path must not be empty"
  [ -n "$source" ] || die "copy source path must not be empty"
  local abs_path="$ROOT_DIR/$path"
  local abs_source="$ROOT_DIR/$source"
  [ "$(realpath -m "$abs_path")" != "$ROOT_DIR" ] || die "copy target must not be repository root"
  [ -e "$abs_source" ] || die "copy source '$source' does not exist"
  if [ -d "$abs_path" ] && [ ! -L "$abs_path" ]; then
    parent_remove_tree "$abs_path"
  elif [ -e "$abs_path" ] || [ -L "$abs_path" ]; then
    parent_remove_file "$abs_path"
  fi
  parent_ensure_dir "$(dirname "$abs_path")"
  project_copy_source "$abs_source" "$abs_path" | python3 "${SCRIPT_DIR}/agent_tools/parent_root_side_effects.py" \
    write --root "$PARENT_ROOT_DIR" --candidate "$abs_path" --purpose agent-canon-sync >/dev/null
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
      s{tools/agent-canon/}{__PARENT_TOOLS__/}g;
      s{((?:\.\./)+)documents/}{$1vendor/agent-canon/documents/}g;
      s{((?:\.\./)+)issues/}{$1vendor/agent-canon/issues/}g;
      s{((?:\.\./)+)tools/}{$1tools/agent-canon/}g;
      s{(?<![A-Za-z0-9_./-])templates/}{vendor/agent-canon/templates/}g;
      s{(?<![A-Za-z0-9_./-])tools/}{tools/agent-canon/}g;
      s{__CANON_TOOLS__/}{vendor/agent-canon/tools/}g;
      s{__CANON_DOCUMENTS__/}{vendor/agent-canon/documents/}g;
      s{__CANON_TEMPLATES__/}{vendor/agent-canon/templates/}g;
      s{__CANON_ISSUES__/}{vendor/agent-canon/issues/}g;
      s{__DOCUMENTS_TOOLS__/}{documents/tools/}g;
      s{__PARENT_TOOLS__/}{tools/agent-canon/}g;
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
  [ -n "$path" ] || die "regular path must not be empty"
  local abs_path="$ROOT_DIR/$path"
  local abs_source=""
  [ "$(realpath -m "$abs_path")" != "$ROOT_DIR" ] || die "regular target must not be repository root"
  if [ -e "$abs_path" ] && [ ! -L "$abs_path" ] \
    && { [ "$path" != ".vscode" ] || [ -d "$abs_path" ]; }; then
    return
  fi
  if [ -z "$source" ]; then
    if [ -L "$abs_path" ]; then
      # Remove legacy whole-directory views before child links materialize.
      # Do not create an empty parent; the child surface creates it safely.
      parent_remove_file "$abs_path"
    fi
    return
  fi
  [ -n "$source" ] || die "regular path '$path' is missing or is a symlink and has no seed source"
  abs_source="$ROOT_DIR/$source"
  [ -e "$abs_source" ] || die "regular seed source '$source' does not exist"
  parent_remove_tree "$abs_path"
  parent_ensure_dir "$(dirname "$abs_path")"
  parent_copy_file "$abs_source" "$abs_path"
}

path_is_tracked_in_head() {
  local path="$1"
  git -C "$ROOT_DIR" cat-file -e "HEAD:$path" >/dev/null 2>&1
}

is_agentcanon_root_view_target() {
  local link_path="$1"
  local target="${2:-}"
  local resolved_target=""
  local resolved_prefix=""

  # A standalone source checkout has PREFIX='.'; its root is the whole
  # repository, so no parent retired-path symlink may be classified here.
  if [ "$PREFIX" = "." ] && ! is_submodule_prefix; then
    return 1
  fi
  [ -n "$target" ] || return 1
  if [[ "$target" = /* ]]; then
    resolved_target="$target"
  else
    resolved_target="$(dirname "$link_path")/$target"
  fi
  resolved_target="$(realpath -m -- "$resolved_target" 2>/dev/null || true)"
  resolved_prefix="$(realpath -m -- "$ROOT_DIR/$PREFIX" 2>/dev/null || true)"
  [ -n "$resolved_target" ] && [ -n "$resolved_prefix" ] || return 1
  case "$resolved_target" in
    "$resolved_prefix"|"$resolved_prefix"/*)
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
    is_agentcanon_root_view_target "$abs_path" "$target" || continue
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

  parent_prefix_head="$(submodule_stage0_gitlink_oid 2>/dev/null && printf '%s\n' "$SUBMODULE_STAGE0_SHA" || true)"
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
  require_live_surface_selection
  ensure_prefix_exists
  assert_parent_submodule_projection_ready || {
    local projection_rc="$?"
    local next_action=""
    if [ "$projection_rc" -eq 1 ]; then
      next_action="prepare_generic_repository_topic_clone_via_dependency_decorator"
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
  preflight_root_copy_transition
  ensure_surface_sync_safe "$force"
  migrate_root_copy_transition

  local spec=""
  # Materialize regular containers before child links. This converts legacy
  # whole-directory symlinks first, so child operations cannot delete files in
  # the AgentCanon source checkout through the old directory link.
  while IFS= read -r spec; do
    [ -n "$spec" ] || continue
    local path="${spec%%:*}"
    local source="${spec#*:}"
    regular_path "$path" "$source"
  done < <(build_regular_specs)

  while IFS= read -r spec; do
    [ -n "$spec" ] || continue
    local path="${spec%%:*}"
    local target="${spec#*:}"
    link_path "$path" "$target"
  done < <(build_link_specs)

  while IFS= read -r spec; do
    [ -n "$spec" ] || continue
    local path="${spec%%:*}"
    local source="${spec#*:}"
    copy_path "$path" "$source"
  done < <(build_copy_specs)

  while IFS= read -r path; do
    [ -n "$path" ] || continue
    # Retired shared views may only be removed when they are still symlinks.
    # A regular path belongs to the parent and is preserved.
    local abs_path="$ROOT_DIR/$path"
    local target=""
    if [ -L "$abs_path" ]; then
      target="$(readlink "$abs_path")"
    fi
    if [ -L "$abs_path" ] && is_agentcanon_root_view_target "$abs_path" "$target"; then
      parent_remove_file "$ROOT_DIR/$path"
    fi
  done < <(build_root_absent_paths)

  ensure_repo_local_goal
}

cmd_snapshot() {
  echo "agent_canon_snapshot_alias=deprecated_use_link_root"
  cmd_link_root
}

cmd_check() {
  require_live_surface_selection
  ensure_prefix_exists

  if ! is_submodule_prefix && [ "$PREFIX" = "." ]; then
    python3 "$ROOT_DIR/tools/agent_tools/surface_manifest.py" \
      --root "$ROOT_DIR" --prefix "." --manifest "$SURFACE_MANIFEST" check-doc
    echo "shared surface source manifest is valid"
    return 0
  fi

  local spec=""
  local failed=0
  local projection_rc=0

  while IFS= read -r spec; do
    [ -n "$spec" ] || continue
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
    [ -n "$spec" ] || continue
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
    [ -n "$spec" ] || continue
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
    local target=""
    if [ -L "$abs_path" ]; then
      target="$(readlink "$abs_path")"
    fi
    if [ -L "$abs_path" ] && is_agentcanon_root_view_target "$abs_path" "$target"; then
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
      echo "NEXT_ACTION=prepare_generic_repository_topic_clone_via_dependency_decorator"
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
    die "shared surface drift detected; set AGENT_CANON_COMMIT_REQUEST_EVIDENCE=evidence:<sha256-of-exact-authorization-evidence-bytes> and rerun '$PUBLIC_SYNC_COMMAND link-root'"
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
    if [ ! -e "$ROOT_DIR/$spec" ] && [ ! -L "$ROOT_DIR/$spec" ] \
      && path_is_tracked_in_head "$spec"; then
      git -C "$ROOT_DIR" add -A -- "$spec"
    fi
  done < <(build_root_absent_paths)
  for spec in "${ROOT_COPY_TRANSITION_REMOVED_PATHS[@]}"; do
    if [ ! -e "$ROOT_DIR/$spec" ] && [ ! -L "$ROOT_DIR/$spec" ] \
      && path_is_tracked_in_head "$spec"; then
      git -C "$ROOT_DIR" add -A -- "$spec"
    fi
  done
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
    if [ ! -e "$ROOT_DIR/$spec" ] && [ ! -L "$ROOT_DIR/$spec" ] \
      && path_is_tracked_in_head "$spec"; then
      owned_paths+=("$spec")
    fi
  done < <(build_root_absent_paths)
  for spec in "${ROOT_COPY_TRANSITION_REMOVED_PATHS[@]}"; do
    if [ ! -e "$ROOT_DIR/$spec" ] && [ ! -L "$ROOT_DIR/$spec" ] \
      && path_is_tracked_in_head "$spec"; then
      owned_paths+=("$spec")
    fi
  done

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
    --trailer "AgentCanon-Authority-Source=${AGENT_CANON_BRANCH_WORKTREE_AUTHORITY:-not-required}" \
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
AgentCanon-Authority-Source: ${AGENT_CANON_BRANCH_WORKTREE_AUTHORITY:-not-required}
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
        parent_remove_file "$ROOT_DIR/$PREFIX/$path"
        ;;
      *)
        parent_checkout_index "$PREFIX/$path" "$ROOT_DIR/$PREFIX/$path"
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
  echo "agent_canon_plan_remote_resolution_status=${REMOTE_RESOLUTION_STATUS:-not_attempted}"
  echo "agent_canon_plan_remote_error_kind=${REMOTE_RESOLUTION_ERROR_KIND:-none}"
  printf 'agent_canon_plan_remote_error_detail=%q\n' "${REMOTE_RESOLUTION_ERROR_DETAIL:-}"
  echo "agent_canon_plan_remote_object_status=${REMOTE_OBJECT_STATUS:-not_attempted}"
  echo "agent_canon_plan_remote_snapshot_start_sha=${REMOTE_SNAPSHOT_START_SHA:-<unavailable>}"
  echo "agent_canon_plan_remote_snapshot_end_sha=${REMOTE_SNAPSHOT_END_SHA:-<unavailable>}"
  echo "agent_canon_plan_remote_snapshot_selected_sha=${REMOTE_SNAPSHOT_SELECTED_SHA:-<unavailable>}"
  echo "agent_canon_plan_remote_snapshot_coherence=${REMOTE_SNAPSHOT_COHERENCE:-not_attempted}"
  echo "agent_canon_plan_remote_probe_status=${REMOTE_PROBE_STATUS:-not_attempted}"
  echo "agent_canon_plan_remote_probe_error_kind=${REMOTE_PROBE_ERROR_KIND:-none}"
  printf 'agent_canon_plan_remote_probe_error_detail=%q\n' "${REMOTE_PROBE_ERROR_DETAIL:-}"
  echo "agent_canon_plan_remote_probe_cleanup_status=${REMOTE_PROBE_CLEANUP_STATUS:-not_attempted}"
  if [ -n "${REMOTE_PROBE_PATH:-}" ]; then
    printf 'agent_canon_plan_remote_probe_path=%q\n' "$REMOTE_PROBE_PATH"
  else
    echo "agent_canon_plan_remote_probe_path=<none>"
  fi
  echo "agent_canon_plan_remote_object_error_kind=${REMOTE_OBJECT_ERROR_KIND:-none}"
  printf 'agent_canon_plan_remote_object_error_detail=%q\n' "${REMOTE_OBJECT_ERROR_DETAIL:-}"
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
    submodule_detached|submodule_detached_dirty|submodule_detached_nonpin|submodule_detached_requires_main|submodule_detached_invalid_stage0_gitlink|submodule_detached_main_descendant|submodule_detached_main_divergent|submodule_detached_main_worktree_collision|submodule_remote_resolution_failed|submodule_remote_object_unavailable|submodule_remote_probe_cleanup_failed|submodule_origin_main_mismatch|remote_resolution_failed|remote_object_unavailable|remote_probe_cleanup_failed|unresolved_submodule_merge_conflict|submodule_merge_conflict|submodule_materialization_collision) ;;
    *)
      echo "agent_canon_plan_apply_command=AGENT_CANON_COMMIT_REQUEST_EVIDENCE=evidence:<sha256-of-exact-authorization-evidence-bytes> $PUBLIC_SYNC_COMMAND ensure-latest $branch"
      ;;
  esac
}

print_submodule_plan_details() {
  local deferred_branch=""
  local deferred_remote_branch=""

  echo "agent_canon_plan_submodule_local_state_checked=yes"
  echo "agent_canon_plan_submodule_parent_pin=$local_tree"
  echo "agent_canon_plan_submodule_parent_head_pin=${parent_head_pin:-<unavailable>}"
  echo "agent_canon_plan_submodule_stage0_mode=$stage0_mode"
  echo "agent_canon_plan_submodule_stage0_stage=$stage0_stage"
  echo "agent_canon_plan_submodule_stage0_path=$stage0_path"
  echo "agent_canon_plan_submodule_stage0_oid=${stage0_oid:-<unavailable>}"
  echo "agent_canon_plan_submodule_stage0_error_kind=${SUBMODULE_STAGE0_ERROR_KIND:-none}"
  printf 'agent_canon_plan_submodule_stage0_error_detail=%q\n' "${SUBMODULE_STAGE0_ERROR_DETAIL:-}"
  echo "agent_canon_plan_submodule_worktree_head=${submodule_worktree_head:-<unavailable>}"
  echo "agent_canon_plan_submodule_worktree_status=$submodule_worktree_status"
  echo "agent_canon_plan_submodule_branch=${submodule_worktree_branch:-<detached>}"
  echo "agent_canon_plan_submodule_main_ref_state=$main_ref_state"
  if [ -n "$main_worktree_collision_path" ]; then
    printf 'agent_canon_plan_submodule_main_worktree_collision_path=%q\n' "$main_worktree_collision_path"
  else
    echo "agent_canon_plan_submodule_main_worktree_collision_path=<none>"
  fi
  echo "agent_canon_plan_submodule_remote_requested_url=${remote_url:-<unset>}"
  echo "agent_canon_plan_submodule_remote_requested_branch=${branch:-<unset>}"
  echo "agent_canon_plan_submodule_remote_resolution_status=${REMOTE_RESOLUTION_STATUS:-not_attempted}"
  echo "agent_canon_plan_submodule_remote_error_kind=${REMOTE_RESOLUTION_ERROR_KIND:-none}"
  printf 'agent_canon_plan_submodule_remote_error_detail=%q\n' "${REMOTE_RESOLUTION_ERROR_DETAIL:-}"
  echo "agent_canon_plan_submodule_remote_object_status=${REMOTE_OBJECT_STATUS:-not_attempted}"
  echo "agent_canon_plan_submodule_remote_object_fetch_attempted=${REMOTE_OBJECT_FETCH_ATTEMPTED:-no}"
  echo "agent_canon_plan_submodule_remote_object_error_kind=${REMOTE_OBJECT_ERROR_KIND:-none}"
  printf 'agent_canon_plan_submodule_remote_object_error_detail=%q\n' "${REMOTE_OBJECT_ERROR_DETAIL:-}"
  echo "agent_canon_plan_submodule_remote_snapshot_start_sha=${REMOTE_SNAPSHOT_START_SHA:-<unavailable>}"
  echo "agent_canon_plan_submodule_remote_snapshot_end_sha=${REMOTE_SNAPSHOT_END_SHA:-<unavailable>}"
  echo "agent_canon_plan_submodule_remote_snapshot_selected_sha=${REMOTE_SNAPSHOT_SELECTED_SHA:-<unavailable>}"
  echo "agent_canon_plan_submodule_remote_snapshot_coherence=${REMOTE_SNAPSHOT_COHERENCE:-not_attempted}"
  echo "agent_canon_plan_submodule_remote_probe_status=${REMOTE_PROBE_STATUS:-not_attempted}"
  echo "agent_canon_plan_submodule_remote_probe_error_kind=${REMOTE_PROBE_ERROR_KIND:-none}"
  printf 'agent_canon_plan_submodule_remote_probe_error_detail=%q\n' "${REMOTE_PROBE_ERROR_DETAIL:-}"
  echo "agent_canon_plan_submodule_remote_probe_cleanup_status=${REMOTE_PROBE_CLEANUP_STATUS:-not_attempted}"
  if [ -n "${REMOTE_PROBE_PATH:-}" ]; then
    printf 'agent_canon_plan_submodule_remote_probe_path=%q\n' "$REMOTE_PROBE_PATH"
  else
    echo "agent_canon_plan_submodule_remote_probe_path=<none>"
  fi
  echo "agent_canon_plan_submodule_origin_main_status=${REMOTE_TRACKING_STATUS:-not_attempted}"
  echo "agent_canon_plan_submodule_origin_main_error_kind=${REMOTE_TRACKING_ERROR_KIND:-none}"
  printf 'agent_canon_plan_submodule_origin_main_error_detail=%q\n' "${REMOTE_TRACKING_ERROR_DETAIL:-}"
  echo "agent_canon_plan_submodule_origin_main_url=${remote_url:-<unset>}"
  echo "agent_canon_plan_submodule_origin_main_branch=${branch:-<unset>}"
  echo "agent_canon_plan_submodule_origin_main_expected_sha=${REMOTE_TRACKING_EXPECTED_SHA:-<unavailable>}"
  echo "agent_canon_plan_submodule_origin_main_fetched_sha=${REMOTE_TRACKING_FETCHED_SHA:-<unavailable>}"
  echo "agent_canon_plan_submodule_history_state=$submodule_history"
  echo "agent_canon_plan_unresolved_merge_conflict=$unresolved_merge_conflict"
  echo "agent_canon_plan_merge_conflict=$merge_conflict"
  if [ "$unresolved_merge_conflict" = "yes" ]; then
    echo "agent_canon_plan_merge_conflict_type=existing_unresolved_index"
  elif [ "$merge_conflict" = "yes" ]; then
    echo "agent_canon_plan_merge_conflict_type=virtual_merge_result"
  else
    echo "agent_canon_plan_merge_conflict_type=none"
  fi
  echo "agent_canon_plan_materialization_collision=$materialization_collision"
  echo "agent_canon_plan_acceptance_predicate=materialization_merge_conflict_or_unpreservable_materialization_collision"
  if [ -n "$materialization_collision_path" ]; then
    printf 'agent_canon_plan_materialization_collision_path=%q\n' "$materialization_collision_path"
  else
    echo "agent_canon_plan_materialization_collision_path=<none>"
  fi
  if [ -n "$submodule_deferred_ref" ]; then
    deferred_branch="${submodule_deferred_ref%%:*}"
    deferred_remote_branch="${submodule_deferred_ref#*:}"
    echo "agent_canon_plan_submodule_deferred_branch=$deferred_branch"
    echo "agent_canon_plan_submodule_deferred_remote_branch=$deferred_remote_branch"
    echo "agent_canon_plan_submodule_deferred_remote_branch_match=yes"
  elif [ -n "$submodule_worktree_branch" ] && [ "$submodule_worktree_branch" != "$DEFAULT_BRANCH" ]; then
    echo "agent_canon_plan_submodule_deferred_branch=$submodule_worktree_branch"
    echo "agent_canon_plan_submodule_deferred_remote_branch=<none>"
    echo "agent_canon_plan_submodule_deferred_remote_branch_match=no"
  else
    echo "agent_canon_plan_submodule_deferred_branch=<none>"
    echo "agent_canon_plan_submodule_deferred_remote_branch=<none>"
    echo "agent_canon_plan_submodule_deferred_remote_branch_match=no"
  fi
  if [ -n "$remote_sha" ]; then
    if [ "$local_tree" = "$remote_sha" ]; then
      echo "agent_canon_plan_submodule_parent_pin_remote_match=yes"
    else
      echo "agent_canon_plan_submodule_parent_pin_remote_match=no"
    fi
    if [ -n "$submodule_worktree_head" ] && [ "$submodule_worktree_head" = "$remote_sha" ]; then
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
  require_live_surface_selection
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
  local submodule_history="unknown"
  local unresolved_merge_conflict="no"
  local merge_conflict="no"
  local materialization_collision="no"
  local materialization_collision_path=""
  local materialization_result_tree=""
  local materialization_result_tree_rc=0
  local materialization_collision_rc=0
  local stage0_rc=0
  local stage0_mode="<unavailable>"
  local stage0_stage="<unavailable>"
  local stage0_path="<unavailable>"
  local stage0_oid=""
  local parent_head_pin=""
  local main_ref_state="unknown"
  local main_worktree_collision_path=""
  local detached_safe="no"
  local fetch_output=""
  local probe_cleanup_rc=0

  REMOTE_RESOLUTION_STATUS="not_attempted"
  REMOTE_RESOLUTION_ERROR_KIND="none"
  REMOTE_RESOLUTION_ERROR_DETAIL=""
  REMOTE_OBJECT_STATUS="not_attempted"
  REMOTE_OBJECT_ERROR_KIND="none"
  REMOTE_OBJECT_ERROR_DETAIL=""
  REMOTE_TRACKING_STATUS="not_attempted"
  REMOTE_TRACKING_ERROR_KIND="none"
  REMOTE_TRACKING_ERROR_DETAIL=""
  REMOTE_TRACKING_EXPECTED_SHA=""
  REMOTE_TRACKING_FETCHED_SHA=""
  REMOTE_TRACKING_URL=""
  REMOTE_TRACKING_BRANCH=""
  REMOTE_SNAPSHOT_START_SHA=""
  REMOTE_SNAPSHOT_END_SHA=""
  REMOTE_SNAPSHOT_SELECTED_SHA=""
  REMOTE_SNAPSHOT_COHERENCE="not_attempted"
  REMOTE_PROBE_STATUS="not_attempted"
  REMOTE_PROBE_ERROR_KIND="none"
  REMOTE_PROBE_ERROR_DETAIL=""
  REMOTE_PROBE_TREE=""
  REMOTE_PROBE_RESULT_TREE=""
  REMOTE_PROBE_HISTORY_STATE="unknown"
  REMOTE_PROBE_COLLISION_PATH=""
  REMOTE_PROBE_CLEANUP_STATUS="not_attempted"
  REMOTE_PROBE_PATH=""
  REMOTE_PROBE_OBJECTS=""
  PLAN_REMOTE_ALTERNATES_PREVIOUS="${GIT_ALTERNATE_OBJECT_DIRECTORIES:-}"

  if is_submodule_prefix; then
    prefix_mode="submodule"
    parent_head_pin="$(submodule_parent_head_pin)"
    if ! submodule_stage0_gitlink_oid; then
      stage0_rc=1
    fi
    stage0_mode="$SUBMODULE_STAGE0_MODE"
    stage0_stage="$SUBMODULE_STAGE0_STAGE"
    stage0_path="$SUBMODULE_STAGE0_PATH"
    stage0_oid="$SUBMODULE_STAGE0_SHA"
    if [ "$stage0_rc" -eq 0 ]; then
      local_tree="$stage0_oid"
    else
      local_tree="${parent_head_pin:-<unavailable>}"
    fi
    local_split=""
    remote_url="$(submodule_remote_url)"
    if ! submodule_checkout_initialized; then
      print_plan_summary \
        "$branch" "$remote_url" "submodule" "" "" "$local_tree" \
        "" "$subtree_metadata" "submodule_checkout_uninitialized" "$dirty" "yes" "$prefix_mode" "no"
      print_submodule_plan_details
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

  if [ "$prefix_mode" = "submodule" ]; then
    remote_source="submodule"
  elif [ -n "$PLAN_REMOTE_OVERRIDE_URL" ]; then
    remote_url="$PLAN_REMOTE_OVERRIDE_URL"
    remote_source="plan_override"
  elif git -C "$ROOT_DIR" remote get-url "$REMOTE_NAME" >/dev/null 2>&1; then
    remote_url="$(git -C "$ROOT_DIR" remote get-url "$REMOTE_NAME")"
    remote_source="configured"
  else
    remote_url="$(default_remote_url)"
    if [ -n "$remote_url" ]; then
      remote_source="default"
    fi
  fi

  if [ "$prefix_mode" = "submodule" ] && [ "$stage0_rc" -ne 0 ]; then
    route="submodule_detached_invalid_stage0_gitlink"
    print_plan_summary \
      "$branch" "$remote_url" "$remote_source" "" "" "$local_tree" \
      "$local_split" "$subtree_metadata" "$route" "$dirty" "yes" "$prefix_mode" "$dirty_update_surface"
    print_submodule_plan_details
    echo "agent_canon_plan_status=blocked"
    echo "NEXT_ACTION=repair_parent_stage0_gitlink_then_rerun_agent_canon_plan"
    return 2
  fi

  if [ "$prefix_mode" = "submodule" ] && [ -z "$submodule_worktree_branch" ]; then
    if [ "$submodule_worktree_status" = "dirty" ]; then
      route="submodule_detached_dirty"
    elif [ "$submodule_worktree_head" != "$stage0_oid" ]; then
      route="submodule_detached_nonpin"
    elif [ "$branch" != "$DEFAULT_BRANCH" ]; then
      route="submodule_detached_requires_main"
    else
      main_ref_state="$(submodule_main_ref_state "$stage0_oid")"
      main_worktree_collision_path="$(submodule_main_worktree_collision_path || true)"
      case "$main_ref_state" in
        absent|same|ancestor)
          if [ -n "$main_worktree_collision_path" ]; then
            route="submodule_detached_main_worktree_collision"
          else
            detached_safe="yes"
          fi
          ;;
        descendant) route="submodule_detached_main_descendant" ;;
        divergent) route="submodule_detached_main_divergent" ;;
        *) route="submodule_detached_main_divergent" ;;
      esac
    fi
    if [ "$detached_safe" != "yes" ]; then
      print_plan_summary \
        "$branch" "$remote_url" "$remote_source" "" "" "$local_tree" \
        "$local_split" "$subtree_metadata" "$route" "$dirty" "yes" "$prefix_mode" "$dirty_update_surface"
      print_submodule_plan_details
      echo "agent_canon_plan_status=blocked"
      case "$route" in
        submodule_detached_dirty) echo "NEXT_ACTION=clean_detached_submodule_without_changing_the_staged_pin" ;;
        submodule_detached_nonpin) echo "NEXT_ACTION=select_source_or_pin_owner_then_repair_detached_submodule" ;;
        submodule_detached_requires_main) echo "NEXT_ACTION=request_default_main_for_detached_submodule_update" ;;
        submodule_detached_main_worktree_collision) echo "NEXT_ACTION=release_main_worktree_collision_then_rerun_agent_canon_plan" ;;
        *) echo "NEXT_ACTION=preserve_unsafe_local_main_ref_then_route_agentcanon_update" ;;
      esac
      return 2
    fi
  fi

  if [ -z "$remote_url" ]; then
    if [ "$prefix_mode" = "submodule" ]; then
      route="submodule_remote_resolution_failed"
      REMOTE_RESOLUTION_STATUS="unreachable"
      REMOTE_RESOLUTION_ERROR_KIND="missing_gitmodules_url"
      REMOTE_RESOLUTION_ERROR_DETAIL="submodule '$PREFIX' has no .gitmodules url"
    fi
    print_plan_summary \
      "$branch" "$remote_url" "$remote_source" "$remote_sha" "$remote_tree" "$local_tree" \
      "$local_split" "$subtree_metadata" "$route" "$dirty" "$requires_clean" "$prefix_mode" "$dirty_update_surface"
    if [ "$prefix_mode" = "submodule" ]; then
      print_submodule_plan_details
    fi
    if [ "$route" = "submodule_remote_resolution_failed" ]; then
      echo "agent_canon_plan_status=blocked"
      echo "NEXT_ACTION=repair_agentcanon_remote_resolution_then_rerun_plan"
      return 2
    fi
    return 0
  fi

  if [ "$prefix_mode" = "submodule" ]; then
    if ! plan_remote_probe "$ROOT_DIR/$PREFIX" "$remote_url" "$branch" "$submodule_worktree_head"; then
      probe_cleanup_rc=0
      if [ "$REMOTE_PROBE_CLEANUP_STATUS" = "failed" ]; then
        probe_cleanup_rc=1
      elif [ -n "$REMOTE_PROBE_PATH" ]; then
        plan_remote_probe_cleanup || probe_cleanup_rc=$?
      fi
      if [ "$probe_cleanup_rc" -ne 0 ]; then
        route="submodule_remote_probe_cleanup_failed"
      elif [ "$REMOTE_PROBE_STATUS" = "merge_conflict" ]; then
        route="submodule_merge_conflict"
      elif [ "$REMOTE_PROBE_STATUS" = "object_unavailable" ]; then
        route="submodule_remote_object_unavailable"
      else
        route="submodule_remote_resolution_failed"
      fi
      print_plan_summary "$branch" "$remote_url" "$remote_source" "${REMOTE_SNAPSHOT_SELECTED_SHA:-}" "${REMOTE_PROBE_TREE:-}" "$local_tree" "$local_split" "$subtree_metadata" "$route" "$dirty" "yes" "$prefix_mode" "$dirty_update_surface"
      print_submodule_plan_details
      echo "agent_canon_plan_status=blocked"
      if [ "$route" = "submodule_remote_probe_cleanup_failed" ]; then
        echo "NEXT_ACTION=preserve_probe_evidence_then_repair_agentcanon_remote_probe_cleanup"
        return 3
      fi
      echo "NEXT_ACTION=repair_agentcanon_remote_probe_then_rerun_plan"
      return 2
    fi
    remote_sha="$REMOTE_SNAPSHOT_SELECTED_SHA"
    remote_tree="$REMOTE_PROBE_TREE"
    export GIT_ALTERNATE_OBJECT_DIRECTORIES="$REMOTE_PROBE_OBJECTS"
    submodule_history="$REMOTE_PROBE_HISTORY_STATE"
    if [ "$REMOTE_TRACKING_STATUS" = "mismatch" ]; then
      route="submodule_origin_main_mismatch"
    fi
    if [ "$route" = "submodule_origin_main_mismatch" ]; then
      # Remote/tracking readback is an earlier blocker.  Do not ask the
      # materialization owner for a merge tree that cannot affect this route.
      :
    elif submodule_unresolved_merge_conflict; then
      unresolved_merge_conflict="yes"
    elif [ -n "$REMOTE_PROBE_RESULT_TREE" ]; then
      materialization_result_tree="$REMOTE_PROBE_RESULT_TREE"
      if [ -n "$REMOTE_PROBE_COLLISION_PATH" ]; then
        materialization_collision="yes"
        materialization_collision_path="$REMOTE_PROBE_COLLISION_PATH"
      fi
    fi
  else
    if ! plan_remote_probe "$ROOT_DIR" "$remote_url" "$branch" "$local_tree"; then
      probe_cleanup_rc=0
      if [ "$REMOTE_PROBE_CLEANUP_STATUS" = "failed" ]; then
        probe_cleanup_rc=1
      elif [ -n "$REMOTE_PROBE_PATH" ]; then
        plan_remote_probe_cleanup || probe_cleanup_rc=$?
      fi
      if [ "$probe_cleanup_rc" -ne 0 ]; then
        route="remote_probe_cleanup_failed"
      elif [ "$REMOTE_PROBE_STATUS" = "object_unavailable" ]; then
        route="remote_object_unavailable"
      else
        route="remote_resolution_failed"
      fi
      print_plan_summary "$branch" "$remote_url" "$remote_source" "${REMOTE_SNAPSHOT_SELECTED_SHA:-}" "${REMOTE_PROBE_TREE:-}" "$local_tree" "$local_split" "$subtree_metadata" "$route" "$dirty" "yes" "$prefix_mode" "$dirty_update_surface"
      echo "agent_canon_plan_status=blocked"
      if [ "$route" = "remote_probe_cleanup_failed" ]; then
        echo "NEXT_ACTION=preserve_probe_evidence_then_repair_agentcanon_remote_probe_cleanup"
        return 3
      fi
      echo "NEXT_ACTION=repair_agentcanon_remote_probe_then_rerun_plan"
      return 2
    fi
    remote_sha="$REMOTE_SNAPSHOT_SELECTED_SHA"
    remote_tree="$REMOTE_PROBE_TREE"
    export GIT_ALTERNATE_OBJECT_DIRECTORIES="$REMOTE_PROBE_OBJECTS"
  fi

  if [ "$prefix_mode" = "submodule" ]; then
    if [ "$route" = "submodule_origin_main_mismatch" ]; then
      :
    elif [ "$unresolved_merge_conflict" = "yes" ]; then
      route="unresolved_submodule_merge_conflict"
    elif [ "$merge_conflict" = "yes" ]; then
      route="submodule_merge_conflict"
    elif [ "$materialization_collision" = "yes" ]; then
      route="submodule_materialization_collision"
    elif [ "$detached_safe" = "yes" ]; then
      route="submodule_detached_parent_pin"
    elif [ -n "$submodule_worktree_branch" ] \
      && [ "$submodule_worktree_branch" != "$DEFAULT_BRANCH" ]; then
      submodule_deferred_ref="$(submodule_pushed_branch_ref "$submodule_worktree_head" || true)"
      route="deferred_branch_pr"
    elif [ "$local_tree" != "$submodule_worktree_head" ] \
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
    else
      route="diverged_submodule_history"
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

  probe_cleanup_rc=0
  if [ "$REMOTE_PROBE_CLEANUP_STATUS" = "failed" ]; then
    probe_cleanup_rc=1
  elif [ -n "$REMOTE_PROBE_PATH" ]; then
    plan_remote_probe_cleanup || probe_cleanup_rc=$?
  fi
  if [ "$probe_cleanup_rc" -ne 0 ]; then
    if [ "$prefix_mode" = "submodule" ]; then
      route="submodule_remote_probe_cleanup_failed"
    else
      route="remote_probe_cleanup_failed"
    fi
  fi
  print_plan_summary \
    "$branch" "$remote_url" "$remote_source" "$remote_sha" "$remote_tree" "$local_tree" \
    "$local_split" "$subtree_metadata" "$route" "$dirty" "$requires_clean" "$prefix_mode" "$dirty_update_surface"
  if [ "$prefix_mode" = "submodule" ]; then
    print_submodule_plan_details
  fi
  case "$route" in
    submodule_remote_probe_cleanup_failed|remote_probe_cleanup_failed)
      echo "agent_canon_plan_status=blocked"
      echo "NEXT_ACTION=preserve_probe_evidence_then_repair_agentcanon_remote_probe_cleanup"
      return 3
      ;;
    submodule_origin_main_mismatch)
      echo "agent_canon_plan_status=blocked"
      echo "NEXT_ACTION=repair_agentcanon_origin_main_tracking_then_rerun_plan"
      return 2
      ;;
    submodule_detached_parent_pin|already_current_submodule|submodule_update|local_contains_remote|deferred_branch_pr|already_current_tree|already_current_split)
      echo "agent_canon_plan_status=ready"
      ;;
    *)
      echo "agent_canon_plan_status=blocked"
      ;;
  esac
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

  pull_log_dir="$(parent_temp_dir "$CANON_PARENT_TMPDIR" pull-log)"
  pull_log="$pull_log_dir/output"
  commit_message="$(automation_commit_message "$remote_sha" "subtree_pull")"
  local pull_output=""
  if pull_output="$(GIT_AUTHOR_NAME="$COMMIT_AUTOMATION_AUTHOR_NAME" \
    GIT_AUTHOR_EMAIL="$COMMIT_AUTOMATION_AUTHOR_EMAIL" \
    GIT_COMMITTER_NAME="$COMMIT_AUTOMATION_AUTHOR_NAME" \
    GIT_COMMITTER_EMAIL="$COMMIT_AUTOMATION_AUTHOR_EMAIL" \
    git -C "$ROOT_DIR" subtree pull --prefix="$PREFIX" "$REMOTE_NAME" "$remote_sha" \
    --squash --message="$commit_message" 2>&1)"; then
    parent_write_file "$pull_log" "$pull_output"
    cat "$pull_log"
    parent_remove_file "$pull_log"
    echo "agent_canon_update_method=subtree_pull"
    cmd_link_root 1
    commit_sync_paths_if_needed "$remote_sha" "subtree_pull"
    return
  fi

  parent_write_file "$pull_log" "$pull_output"
  cat "$pull_log" >&2
  parent_remove_file "$pull_log"
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
  remote_sha="$(require_remote_branch_sha "$REMOTE_NAME" "$branch")"
  require_remote_commit_object "$ROOT_DIR" "$REMOTE_NAME" "$remote_sha"
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

  require_live_surface_selection
  ensure_prefix_exists
  if is_submodule_prefix; then
    local remote_url="" local_commit="" worktree_commit="" origin_sha=""
    local submodule_status="" submodule_remote_branch="" parent_pin_status="current"
    local current_branch="" history_state="" collision_path=""
    local staged_pin="" stage0_rc=0 main_ref_state="" main_collision_path=""
    local materialization_result_tree=""
    local index_entry="" staged_mode="" staged_sha="" staged_stage="" staged_path=""
    local applied_head="" applied_status=""
    local update_state="" materialization_rc=0
    local materialization_result_tree_rc=0 materialization_collision_rc=0

    submodule_checkout_initialized \
      || die "submodule '$PREFIX' checkout is uninitialized; initialize and attach $branch before updating"
    if submodule_unresolved_merge_conflict; then
      echo "agent_canon_materialization_unresolved_merge_conflict=yes"
      echo "agent_canon_materialization_merge_conflict=yes"
      echo "agent_canon_materialization_conflict_type=existing_unresolved_index"
      echo "agent_canon_materialization_result=blocked_unresolved_merge_conflict"
      die "submodule '$PREFIX' update is blocked by an unresolved merge conflict"
    fi
    submodule_status="$(git -C "$ROOT_DIR/$PREFIX" status --porcelain=v1 --untracked-files=all)"
    current_branch="$(git -C "$ROOT_DIR/$PREFIX" symbolic-ref --quiet --short HEAD 2>/dev/null || true)"
    remote_url="$(submodule_remote_url)"
    [ -n "$remote_url" ] || die "submodule '$PREFIX' has no .gitmodules url"
    if ! submodule_stage0_gitlink_oid; then
      stage0_rc=1
    fi
    [ "$stage0_rc" -eq 0 ] || die "$SUBMODULE_STAGE0_ERROR_DETAIL"
    staged_pin="$SUBMODULE_STAGE0_SHA"
    local_commit="$staged_pin"
    worktree_commit="$(git -C "$ROOT_DIR/$PREFIX" rev-parse HEAD)"
    if [ -z "$current_branch" ]; then
      [ "$branch" = "$DEFAULT_BRANCH" ] \
        || die "detached submodule '$PREFIX' requires requested branch '$DEFAULT_BRANCH' for safe attachment"
      [ -z "$submodule_status" ] \
        || die "detached submodule '$PREFIX' is dirty; clean it without changing the staged gitlink before update"
      [ "$worktree_commit" = "$staged_pin" ] \
        || die "detached submodule '$PREFIX' HEAD '$worktree_commit' does not equal stage-0 gitlink '$staged_pin'"
      main_ref_state="$(submodule_main_ref_state "$staged_pin")"
      main_collision_path="$(submodule_main_worktree_collision_path || true)"
      [ -z "$main_collision_path" ] \
        || die "detached submodule '$PREFIX' main is checked out in another worktree '$main_collision_path'"
      case "$main_ref_state" in
        absent|same|ancestor) ;;
        descendant|divergent)
          die "detached submodule '$PREFIX' local main ref is unsafe ($main_ref_state); preserve it and route the update"
          ;;
        *) die "detached submodule '$PREFIX' local main ref state is unavailable" ;;
      esac
      attach_submodule_main_to_staged_pin "$staged_pin" "$remote_url" \
        || die "detached submodule '$PREFIX' could not be safely attached to main"
      current_branch="main"
      worktree_commit="$(git -C "$ROOT_DIR/$PREFIX" rev-parse HEAD)"
    fi
    submodule_remote_branch="$(submodule_remote_branch_for_head "$worktree_commit" || true)"
    remote_sha="$(require_remote_branch_sha "$remote_url" "$branch")"
    git -C "$ROOT_DIR/$PREFIX" fetch --no-write-fetch-head origin \
      "refs/heads/$branch:refs/remotes/origin/$branch" >/dev/null
    origin_sha="$(
      git -C "$ROOT_DIR/$PREFIX" rev-parse --verify "refs/remotes/origin/$branch^{commit}"
    )"
    [ "$origin_sha" = "$remote_sha" ] \
      || die "submodule '$PREFIX' origin/$branch '$origin_sha' does not match expected '$remote_sha'"
    if [ "$local_commit" != "$worktree_commit" ]; then
      parent_pin_status="stale"
    fi
    history_state="$(submodule_history_state "$worktree_commit" "$remote_sha")"

    echo "agent_canon_latest_submodule_local_state_checked=yes"
    echo "agent_canon_latest_submodule_local_state_source=$PREFIX"
    echo "agent_canon_latest_submodule_worktree_status=$([ -n "$submodule_status" ] && echo dirty || echo clean)"
    echo "agent_canon_latest_branch=$current_branch"
    echo "agent_canon_latest_submodule_branch=$current_branch"
    echo "agent_canon_latest_submodule_history_state=$history_state"
    echo "agent_canon_latest_acceptance_predicate=materialization_merge_conflict_or_unpreservable_materialization_collision"
    if [ -n "$submodule_remote_branch" ]; then
      echo "agent_canon_latest_remote_branch=origin/$submodule_remote_branch"
    fi
    echo "agent_canon_local_submodule=$local_commit"
    echo "agent_canon_worktree_submodule=$worktree_commit"
    echo "agent_canon_remote=$remote_sha"
    echo "agent_canon_latest_parent_pin_status=$parent_pin_status"
    materialization_result_tree="$(
      submodule_materialization_result_tree "$worktree_commit" "$remote_sha"
    )" || materialization_result_tree_rc=$?
    if [ "$materialization_result_tree_rc" -eq 2 ]; then
      echo "agent_canon_materialization_unresolved_merge_conflict=no"
      echo "agent_canon_materialization_merge_conflict=yes"
      echo "agent_canon_materialization_conflict_type=virtual_merge_result"
      echo "agent_canon_materialization_result=blocked_merge_conflict"
      die "submodule '$PREFIX' update has a virtual merge-result conflict"
    fi
    [ "$materialization_result_tree_rc" -eq 0 ] \
      || die "failed to compute the AgentCanon virtual merge result tree"
    echo "agent_canon_materialization_unresolved_merge_conflict=no"
    echo "agent_canon_materialization_merge_conflict=no"
    echo "agent_canon_materialization_conflict_type=none"
    collision_path="$(
      submodule_materialization_collision_path "$worktree_commit" "$materialization_result_tree"
    )" || materialization_collision_rc=$?
    if [ "$materialization_collision_rc" -eq 0 ]; then
      echo "agent_canon_materialization_collision=yes"
      printf 'agent_canon_materialization_collision_path=%q\n' "$collision_path"
      echo "agent_canon_materialization_result=blocked_unpreservable_collision"
      die "submodule '$PREFIX' update would overwrite a local materialized path in the exact update write set"
    fi
    [ "$materialization_collision_rc" -eq 1 ] \
      || die "failed to compute the AgentCanon materialization collision set"
    echo "agent_canon_materialization_collision=no"

    if [ "$current_branch" != "$DEFAULT_BRANCH" ]; then
      update_state="deferred_branch_pr"
    elif [ "$local_commit" = "$worktree_commit" ] && [ "$worktree_commit" = "$remote_sha" ]; then
      update_state="already_current_submodule"
    elif [ "$worktree_commit" = "$remote_sha" ]; then
      update_state="parent_pin_pending"
    elif [ "$history_state" = "ahead" ] || [ "$history_state" = "diverged" ]; then
      update_state="deferred_branch_pr"
    else
      update_state="updating_submodule"
    fi
    if [ "$update_state" = "updating_submodule" ]; then
      ensure_surface_sync_safe
    fi
    if [ "$update_state" = "deferred_branch_pr" ]; then
      materialize_submodule_remote_branch \
        "$worktree_commit" "$remote_sha" "$branch" "$materialization_result_tree" \
        || materialization_rc=$?
      [ "$materialization_rc" -eq 0 ] || return "$materialization_rc"
      applied_head="$(git -C "$ROOT_DIR/$PREFIX" rev-parse HEAD)"
      applied_status="$(git -C "$ROOT_DIR/$PREFIX" status --porcelain=v1 --untracked-files=all)"
      echo "agent_canon_latest=deferred_branch_pr"
      echo "agent_canon_latest_submodule_applied_head=$applied_head"
      echo "agent_canon_latest_submodule_applied_upstream=origin/$branch"
      echo "agent_canon_latest_submodule_applied_status=$([ -n "$applied_status" ] && echo dirty_preserved || echo clean)"
      return
    fi

    materialize_submodule_remote_branch \
      "$worktree_commit" "$remote_sha" "$branch" "$materialization_result_tree" \
      || materialization_rc=$?
    [ "$materialization_rc" -eq 0 ] || return "$materialization_rc"
    git -C "$ROOT_DIR" add -A -- "$PREFIX"
    index_entry="$(git -C "$ROOT_DIR" ls-files --stage -- "$PREFIX")"
    read -r staged_mode staged_sha staged_stage staged_path <<<"$index_entry"
    if [ "$(printf '%s\n' "$index_entry" | awk 'NF { count += 1 } END { print count + 0 }')" -ne 1 ] \
      || [ "$staged_mode" != "160000" ] || [ "$staged_stage" != "0" ] \
      || [ "$staged_path" != "$PREFIX" ]; then
      die "submodule '$PREFIX' update did not produce the expected stage-0 gitlink"
    fi
    applied_head="$(git -C "$ROOT_DIR/$PREFIX" rev-parse HEAD)"
    applied_status="$(git -C "$ROOT_DIR/$PREFIX" status --porcelain=v1 --untracked-files=all)"
    [ "$applied_head" = "$staged_sha" ] \
      || die "submodule '$PREFIX' staged-pin readback failed"
    echo "agent_canon_latest=$update_state"
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
    echo "agent_canon_latest_submodule_applied_status=$([ -n "$applied_status" ] && echo dirty_preserved || echo clean)"

    if [ "$update_state" = "already_current_submodule" ]; then
      cmd_link_root 1
      return
    fi
    if [ "$update_state" = "parent_pin_pending" ]; then
      cmd_link_root 1
      commit_sync_paths_if_needed "$remote_sha" "submodule_parent_pin"
      return
    fi
    cmd_link_root
    commit_sync_paths_if_needed "$remote_sha" "submodule_update"
    return
  fi

  ensure_existing_remote_or_default
  remote_sha="$(require_remote_branch_sha "$REMOTE_NAME" "$branch")"
  require_remote_commit_object "$ROOT_DIR" "$REMOTE_NAME" "$remote_sha"
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
    [ -n "$spec" ] || continue
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
    [ -n "$spec" ] || continue
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
    [ -n "$spec" ] || continue
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
