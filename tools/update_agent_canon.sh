#!/usr/bin/env bash
# @dependency-start
# contract tool
# responsibility Provides GitHub-first AgentCanon submodule update automation.
# upstream design ../documents/agent-canon/agent-canon-update-route.md owns update materialization acceptance and publication order.
# upstream design ../documents/contracts/github-first-module-and-devcontainer-policy.md defines GitHub-first module policy.
# upstream design ../documents/rule/repository-topic-clone.md owns the generic topic-clone lifecycle.
# upstream design ../documents/rule/dependency-module-changes.md decorates that lifecycle with pin/projection policy.
# upstream design ../documents/agent-canon/agent-canon-github-remote.md defines the canonical AgentCanon GitHub remote.
# upstream implementation ./sync_agent_canon.sh performs low-level submodule freshness and root-view synchronization.
# upstream implementation ./agent_tools/attach_clean_detached_submodule.py safely attaches a reconstructible detached parent submodule before planning/apply.
# upstream implementation ./agent_tools/update_lifecycle_contract.py owns queue/frontier receipt mechanics and guards.
# upstream implementation ./agent_tools/source_projection_handoff.py materializes the sole source-publication packet in the parent owner namespace.
# upstream implementation ./rebuild_agent_tools.sh rebuilds compiled AgentCanon tools after safe updates.
# downstream implementation ./agent_tools/agent_canon_update_todos.py advances parent-repo AgentCanon update TODO state after safe updates.
# downstream implementation ../tests/tools/test_update_agent_canon.py validates update wrapper behavior.
# @dependency-end

set -euo pipefail
export GIT_TERMINAL_PROMPT="${GIT_TERMINAL_PROMPT:-0}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
source "${SCRIPT_DIR}/lib/repo_paths.sh"
source "${SCRIPT_DIR}/lib/update_materialization.sh"
source "${SCRIPT_DIR}/lib/git_authority.sh"
ROOT_DIR="$(agent_canon_repo_root "${BASH_SOURCE[0]}")"
CANON_TOOLS_ROOT="$(agent_canon_source_tools_root "$ROOT_DIR")"
AGENT_CANON_SOURCE_ROOT="$(git -C "${CANON_TOOLS_ROOT}" rev-parse --show-toplevel)"
PARENT_ROOT_DIR="${AGENT_CANON_PARENT_ROOT:-$ROOT_DIR}"
PARENT_ROOT_DIR="$(cd "${PARENT_ROOT_DIR}" && pwd -P)"
AGENT_CANON_BOUNDARY_SCRIPT="${CANON_TOOLS_ROOT}/agent_tools/parent_root_side_effects.py"

if [[ "${PARENT_ROOT_DIR}" != "${ROOT_DIR}" \
  && "${AGENT_CANON_CHILD_PURPOSE:-}" != "agent-canon-update-script" ]]; then
  echo "AGENT_CANON_UPDATE_PARENT_HANDOFF=missing" >&2
  echo "AGENT_CANON_UPDATE_PARENT_ROOT=${PARENT_ROOT_DIR}" >&2
  echo "AGENT_CANON_UPDATE_SOURCE_ROOT=${AGENT_CANON_SOURCE_ROOT}" >&2
  exit 2
fi
if [[ "${AGENT_CANON_CHILD_PURPOSE:-}" == "agent-canon-update-script" ]]; then
  python3 "${AGENT_CANON_BOUNDARY_SCRIPT}" verify-child \
    --root "${PARENT_ROOT_DIR}" \
    --source-root "${AGENT_CANON_SOURCE_ROOT}" \
    --purpose agent-canon-update-script \
    --consume >/dev/null
else
  exec python3 "${AGENT_CANON_BOUNDARY_SCRIPT}" exec-parent-bound \
    --root "${PARENT_ROOT_DIR}" \
    --source-root "${AGENT_CANON_SOURCE_ROOT}" \
    --purpose agent-canon-update-script \
    --issue-handoff \
    -- bash "${BASH_SOURCE[0]}" "$@"
fi
unset AGENT_CANON_CHILD_HANDOFF AGENT_CANON_HANDOFF_AUDIENCE AGENT_CANON_CHILD_PURPOSE

CANON_PARENT_TMP_CANDIDATE="${AGENT_CANON_PARENT_TMPDIR:-$PARENT_ROOT_DIR/.agent-canon/tmp/update}"
CANON_PARENT_TMPDIR="$(python3 "${CANON_TOOLS_ROOT}/agent_tools/parent_root_side_effects.py" \
  ensure-dir --root "$PARENT_ROOT_DIR" --candidate "$CANON_PARENT_TMP_CANDIDATE" --purpose agent-canon-update)"
export TMPDIR="$CANON_PARENT_TMPDIR"
parent_ensure_dir() {
  python3 "${CANON_TOOLS_ROOT}/agent_tools/parent_root_side_effects.py" \
    ensure-dir --root "$PARENT_ROOT_DIR" --candidate "$1" --purpose "${2:-agent-canon-update}"
}
parent_temp_dir() {
  python3 "${CANON_TOOLS_ROOT}/agent_tools/parent_root_side_effects.py" \
    temp-dir --root "$PARENT_ROOT_DIR" --candidate "$1" --prefix "$2" --purpose "${3:-agent-canon-update}"
}
parent_write_file() {
  local candidate="$1" content="${2-}"
  printf '%s' "$content" | python3 "${CANON_TOOLS_ROOT}/agent_tools/parent_root_side_effects.py" \
    write --root "$PARENT_ROOT_DIR" --candidate "$candidate" --purpose "${3:-agent-canon-update}" >/dev/null
}
parent_remove_file() {
  python3 "${CANON_TOOLS_ROOT}/agent_tools/parent_root_side_effects.py" \
    remove-file --root "$PARENT_ROOT_DIR" --candidate "$1" --purpose "${2:-agent-canon-update}" >/dev/null
}
parent_remove_tree() {
  python3 "${CANON_TOOLS_ROOT}/agent_tools/parent_root_side_effects.py" \
    remove-tree --root "$PARENT_ROOT_DIR" --candidate "$1" --purpose "${2:-agent-canon-update}" >/dev/null
}
parent_copy_file() {
  python3 "${CANON_TOOLS_ROOT}/agent_tools/parent_root_side_effects.py" \
    copy --root "$PARENT_ROOT_DIR" --source "$1" --candidate "$2" --purpose "${3:-agent-canon-update}" >/dev/null
}
parent_move_path() {
  python3 "${CANON_TOOLS_ROOT}/agent_tools/parent_root_side_effects.py" \
    move --root "$PARENT_ROOT_DIR" --source "$1" --candidate "$2" --purpose "${3:-agent-canon-update}" >/dev/null
}
parent_symlink() {
  python3 "${CANON_TOOLS_ROOT}/agent_tools/parent_root_side_effects.py" \
    symlink --root "$PARENT_ROOT_DIR" --target "$1" --candidate "$2" --purpose "${3:-agent-canon-update}" >/dev/null
}
run_parent_bound_sync() {
  AGENT_CANON_ACTIVE_REPOSITORY_ROOT="${PARENT_ROOT_DIR}" \
    python3 "${AGENT_CANON_BOUNDARY_SCRIPT}" exec-parent-bound \
    --root "${PARENT_ROOT_DIR}" \
    --source-root "${AGENT_CANON_SOURCE_ROOT}" \
    --purpose agent-canon-sync-script \
    --issue-handoff \
    -- bash "$CANON_TOOLS_ROOT/sync_agent_canon.sh" "$@"
}
PREFIX="${AGENT_CANON_PREFIX:-vendor/agent-canon}"
SUPERPROJECT_DIR=""
if [ "$(git -C "$ROOT_DIR" config -f .gitmodules --get "submodule.${PREFIX}.path" 2>/dev/null || true)" = "$PREFIX" ] \
  || [ "$ROOT_DIR" != "$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel)" ]; then
  SUPERPROJECT_DIR="$ROOT_DIR"
fi
DEFAULT_BRANCH="${AGENT_CANON_BRANCH:-main}"
PROTECTED_GIT_NEXT_ACTION="request_explicit_user_approval_then_rerun_same_command_with_inline_git_authority_and_reason"
BRANCH_WORKTREE_NEXT_ACTION="request_branch_or_worktree_creation_authority_then_rerun_same_command_with_inline_git_authority_and_reason"
COMMIT_AUTOMATION_AUTHOR_NAME="AgentCanon Sync Automation"
COMMIT_AUTOMATION_AUTHOR_EMAIL="agent-canon-sync@automation.invalid"
COMMIT_PROVENANCE_NEXT_ACTION="set AGENT_CANON_COMMIT_REQUEST_EVIDENCE=evidence:<64 lowercase hex> and rerun the same command"
if [ -n "$SUPERPROJECT_DIR" ]; then
  AGENT_CANON_SOURCE_MODE="parent_projection"
  AGENT_CANON_DIR="$ROOT_DIR/$PREFIX"
else
  AGENT_CANON_SOURCE_MODE="standalone_source"
  AGENT_CANON_DIR="$ROOT_DIR"
fi
UPDATE_OWNER_NAMESPACE="$PARENT_ROOT_DIR/.agent-canon/update-lifecycle"
UPDATE_STATE_DIR="$UPDATE_OWNER_NAMESPACE/state"
UPDATE_EVIDENCE_DIR="$UPDATE_OWNER_NAMESPACE/evidence"
UPDATE_PROJECTION_DIR="$UPDATE_OWNER_NAMESPACE/projection-queue"
SOURCE_PROJECTION_PACKET="$UPDATE_STATE_DIR/source-publication-ready.json"
SOURCE_PROJECTION_HANDOFF="${AGENT_CANON_SOURCE_PROJECTION_HANDOFF:-}"

usage() {
  cat <<EOF
Usage:
  bash tools/update_agent_canon.sh plan [branch]
  AGENT_CANON_COMMIT_REQUEST_EVIDENCE=evidence:<sha256-of-exact-authorization-evidence-bytes> bash tools/update_agent_canon.sh latest [branch]
  AGENT_CANON_COMMIT_REQUEST_EVIDENCE=evidence:<sha256-of-exact-authorization-evidence-bytes> bash tools/update_agent_canon.sh apply [branch]
  bash tools/update_agent_canon.sh rebuild-tools
  AGENT_CANON_COMMIT_REQUEST_EVIDENCE=evidence:<sha256-of-exact-authorization-evidence-bytes> bash tools/update_agent_canon.sh merge-main-into-current [branch]
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
      Fetch AgentCanon main and merge it into the current source branch while
      preserving non-colliding local uncommitted paths in place.
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

protected_git_authority_failure() {
  local mode="$1"
  git_authority_emit_failure \
    "$mode" "$PROTECTED_GIT_NEXT_ACTION" "$BRANCH_WORKTREE_NEXT_ACTION" \
    "protected AgentCanon update requires same-command"
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

ensure_agent_canon_submodule() {
  if [ "$AGENT_CANON_SOURCE_MODE" = "standalone_source" ]; then
    git -C "$AGENT_CANON_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1 \
      || die "standalone AgentCanon source is not a Git worktree"
    return
  fi
  [ -d "$ROOT_DIR/$PREFIX" ] || die "prefix '$PREFIX' does not exist"
  [ "$(git -C "$ROOT_DIR" ls-tree HEAD "$PREFIX" 2>/dev/null | awk '{print $1}')" = "160000" ] \
    || die "prefix '$PREFIX' is not a Git submodule"
  if ! git -C "$ROOT_DIR/$PREFIX" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    git -C "$ROOT_DIR" submodule update --init --recursive "$PREFIX" >/dev/null
  fi
}

submodule_remote_url() {
  if [ "$AGENT_CANON_SOURCE_MODE" = "standalone_source" ]; then
    git -C "$AGENT_CANON_DIR" remote get-url origin 2>/dev/null || true
    return
  fi
  git -C "$ROOT_DIR" config -f .gitmodules --get "submodule.${PREFIX}.url" 2>/dev/null || true
}

parent_pin() {
  if [ "$AGENT_CANON_SOURCE_MODE" = "standalone_source" ]; then
    git -C "$AGENT_CANON_DIR" rev-parse HEAD
    return
  fi
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

  if git -C "$AGENT_CANON_DIR" merge-base --is-ancestor "$remote_sha" "$post_head"; then
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
  awk -F= -v key="$key" '$1 == key {print substr($0, index($0, "=") + 1)}' <<< "$text" | tail -n1
}

emit_agentcanon_conflict_workflow_route() {
  local reason="$1"
  local current_checkout_block="no"

  case "$reason" in
    *route=submodule_materialization_collision*|*route=submodule_merge_conflict*|*route=unresolved_submodule_merge_conflict*|*materialization_collision*|*merge_conflict*)
      current_checkout_block="yes"
      ;;
  esac

  if [ "$current_checkout_block" = "yes" ]; then
    echo "AGENT_CANON_LATEST_TOOL_RESULT=blocked_current_checkout"
    echo "AGENT_CANON_LATEST_BLOCK_SCOPE=current_checkout"
    echo "AGENT_CANON_LATEST_BLOCK_REASON=$reason"
    echo "AGENT_CANON_LATEST_WORKFLOW=agents/workflows/derived-agent-canon-diff-workflow.md"
    echo "NEXT_ACTION=resolve_agentcanon_materialization_collision_or_merge_conflict_in_current_checkout_then_rerun_latest"
    return
  fi

  echo "AGENT_CANON_LATEST_TOOL_RESULT=agent_workflow_required"
  echo "AGENT_CANON_LATEST_BLOCK_REASON=$reason"
  echo "AGENT_CANON_LATEST_WORKFLOW=agents/workflows/derived-agent-canon-diff-workflow.md"
  if [ "$AGENT_CANON_SOURCE_MODE" = "parent_projection" ]; then
    echo "AGENT_CANON_LATEST_CLONE_OWNER=tools/agent_tools/repository_topic_clone.py"
    echo "AGENT_CANON_LATEST_DEPENDENCY_ROUTE=python3 tools/agent_tools/dependency_module_change.py --root . prepare --topic <topic> --module $PREFIX --branch <source-branch> --owner-evidence <owner-evidence>"
    echo "NEXT_ACTION=prepare_generic_repository_topic_clone_via_dependency_decorator"
  else
    echo "AGENT_CANON_LATEST_CONFLICT_COMMAND=AGENT_CANON_COMMIT_REQUEST_EVIDENCE=evidence:<sha256-of-exact-authorization-evidence-bytes> bash tools/update_agent_canon.sh merge-main-into-current"
    echo "AGENT_CANON_LATEST_POST_MERGE_COMMAND=AGENT_CANON_COMMIT_REQUEST_EVIDENCE=evidence:<sha256-of-exact-authorization-evidence-bytes> make agent-canon-ensure-latest"
    echo "NEXT_ACTION=run_agentcanon_conflict_workflow"
  fi
}

route_requires_agent_workflow() {
  local route="$1"
  local prefix_mode="$2"

  case "$route" in
    submodule_detached|submodule_detached_dirty|submodule_detached_nonpin|submodule_detached_requires_main|submodule_detached_invalid_stage0_gitlink|submodule_detached_main_descendant|submodule_detached_main_divergent|submodule_detached_main_worktree_collision|submodule_remote_resolution_failed|submodule_remote_object_unavailable|submodule_origin_main_fetch_failed|submodule_origin_main_mismatch|submodule_merge_conflict|submodule_materialization_collision|unresolved_submodule_merge_conflict)
      return 0
      ;;
    deferred_branch_pr)
      return 1
      ;;
    local_contains_remote|diverged_submodule_history)
      if [ "$prefix_mode" = "submodule" ]; then
        return 1
      fi
      return 0
      ;;
    diverged_local_history|snapshot_import_unsafe_tree_not_in_remote)
      return 0
      ;;
  esac
  return 1
}

attach_reconstructible_detached_parent_submodule() {
  local branch="$1"
  if [ "$AGENT_CANON_SOURCE_MODE" != "parent_projection" ]; then
    return 0
  fi
  python3 "$CANON_TOOLS_ROOT/agent_tools/attach_clean_detached_submodule.py" \
    --root "$ROOT_DIR" --prefix "$PREFIX" --branch "$branch"
}

acknowledge_update_todos_if_available() {
  local todo_tool="$CANON_TOOLS_ROOT/agent_tools/agent_canon_update_todos.py"
  local state_path="$ROOT_DIR/.agent-canon/update-state.toml"
  local todo_log=""
  local pending_count=""

  if [ ! -f "$todo_tool" ]; then
    echo "AGENT_CANON_LATEST_TODOS=skipped_missing_tool"
    return 0
  fi

  todo_log_dir="$(parent_temp_dir "$CANON_PARENT_TMPDIR" todo-log)"
  todo_log="$todo_log_dir/output"
  local todo_output=""
  if ! todo_output="$(python3 "$todo_tool" plan --write 2>&1)"; then
    parent_write_file "$todo_log" "$todo_output"
    cat "$todo_log"
    parent_remove_file "$todo_log"
    echo "AGENT_CANON_LATEST_TODOS=failed"
    echo "NEXT_ACTION=repair_agent_canon_update_todo_state_then_rerun_latest"
    return 1
  fi
  parent_write_file "$todo_log" "$todo_output"
  cat "$todo_log"
  pending_count="$(awk -F= '/^AGENT_CANON_UPDATE_TODO_PENDING_COUNT=/{print $2}' "$todo_log")"
  parent_remove_file "$todo_log"

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
      GIT_AUTHOR_NAME="$COMMIT_AUTOMATION_AUTHOR_NAME" \
      GIT_AUTHOR_EMAIL="$COMMIT_AUTOMATION_AUTHOR_EMAIL" \
      GIT_COMMITTER_NAME="$COMMIT_AUTOMATION_AUTHOR_NAME" \
      GIT_COMMITTER_EMAIL="$COMMIT_AUTOMATION_AUTHOR_EMAIL" \
        git -C "$ROOT_DIR" commit --only \
        -m "chore: acknowledge agent-canon update tasks" \
        --trailer "AgentCanon-Automation-Actor=agent-canon-sync" \
        --trailer "AgentCanon-Authority-Source=${AGENT_CANON_BRANCH_WORKTREE_AUTHORITY}" \
        --trailer "AgentCanon-Destructive-Authority=${AGENT_CANON_DESTRUCTIVE_GIT_AUTHORITY}" \
        --trailer "AgentCanon-Request-Evidence=${AGENT_CANON_COMMIT_REQUEST_EVIDENCE}" \
        -- "$state_path"
      echo "AGENT_CANON_LATEST_TODOS=acknowledged_committed"
      return 0
    fi
  fi
  echo "AGENT_CANON_LATEST_TODOS=acknowledged_noop"
}

rebuild_agent_tools_if_available() {
  local rebuild_tool="$CANON_TOOLS_ROOT/rebuild_agent_tools.sh"
  if [ ! -f "$rebuild_tool" ]; then
    echo "AGENT_CANON_TOOL_REBUILD=skipped_missing_tool"
    return
  fi
  AGENT_CANON_ACTIVE_REPOSITORY_ROOT="${PARENT_ROOT_DIR}" \
    python3 "${AGENT_CANON_BOUNDARY_SCRIPT}" exec-parent-bound \
      --root "${PARENT_ROOT_DIR}" \
      --source-root "${AGENT_CANON_SOURCE_ROOT}" \
      --purpose agent-canon-rebuild-script \
      --issue-handoff \
      -- bash "$rebuild_tool"
}

source_projection_lifecycle_complete() {
  [ -f "$UPDATE_STATE_DIR/current-transaction" ] \
    && [ -f "$UPDATE_PROJECTION_DIR/queue.accepted.json" ] \
    && [ -f "$UPDATE_PROJECTION_DIR/frontier.accepted.json" ] \
    && [ -f "$UPDATE_EVIDENCE_DIR/g4.parent-projection-integrity.json" ]
}

materialize_source_projection_handoff() {
  local handoff="${SOURCE_PROJECTION_HANDOFF:-}"
  if [ -z "$handoff" ]; then
    return 0
  fi
  [ -f "$handoff" ] \
    || die "source projection handoff input is missing: $handoff"
  PYTHONPATH="$CANON_TOOLS_ROOT/agent_tools${PYTHONPATH:+:$PYTHONPATH}" \
    python3 "$CANON_TOOLS_ROOT/agent_tools/source_projection_handoff.py" publish \
      --root "$PARENT_ROOT_DIR" \
      --input "$handoff" \
      --output "$SOURCE_PROJECTION_PACKET"
}

ensure_source_projection_lifecycle() {
  if source_projection_lifecycle_complete; then
    return 0
  fi
  materialize_source_projection_handoff
  if [ -f "$SOURCE_PROJECTION_PACKET" ]; then
    advance_source_projection
  fi
  if source_projection_lifecycle_complete; then
    return 0
  fi
  echo "AGENT_CANON_PARENT_PROJECTION_BLOCKER=source_publication_handoff_missing" >&2
  echo "AGENT_CANON_SOURCE_PROJECTION_PACKET=$SOURCE_PROJECTION_PACKET" >&2
  echo "NEXT_ACTION=publish_source_projection_packet_via_canonical_source_front_door;manual_gitlink_or_receipt_copy_forbidden" >&2
  die "parent projection blocked: source publication handoff is missing"
}

emit_queue_receipt() {
  local binding_file="$1"
  local rebind_receipt_file="$2"
  local source_main_readback_evidence_ref="$3"
  local predecessor_388_evidence_ref="$4"
  local predecessor_389_evidence_ref="$5"
  local source_projection_packet="$6"
  local queue_output="${7:-$UPDATE_PROJECTION_DIR/queue.accepted.json}"
  local frontier_output="${8:-$UPDATE_PROJECTION_DIR/frontier.pending.json}"
  local current_marker="$UPDATE_STATE_DIR/current-transaction"

  parent_ensure_dir "$UPDATE_STATE_DIR"
  parent_ensure_dir "$UPDATE_EVIDENCE_DIR"
  parent_ensure_dir "$UPDATE_PROJECTION_DIR"
  PYTHONPATH="$CANON_TOOLS_ROOT/agent_tools${PYTHONPATH:+:$PYTHONPATH}" \
    python3 - "$binding_file" "$rebind_receipt_file" \
      "$source_main_readback_evidence_ref" "$predecessor_388_evidence_ref" \
      "$predecessor_389_evidence_ref" "$source_projection_packet" \
      "$queue_output" "$frontier_output" \
      "$AGENT_CANON_DIR" "$current_marker" "$PARENT_ROOT_DIR" <<'PY'
import json
import sys
from pathlib import Path

from parent_root_side_effects import (
    ParentRootAttestationRequest,
    ParentRootSideEffectBoundary,
)

from update_lifecycle_contract import (
    materialize_dependency_frontier,
    materialize_queue_receipt,
    validate_dependency_frontier,
    validate_immutable_replay,
    validate_queue_receipt,
)

(
    binding_path,
    rebind_path,
    readback_ref,
    predecessor_388_ref,
    predecessor_389_ref,
    packet_path,
    queue_path,
    frontier_path,
    source_namespace,
    current_marker_path,
    root_dir,
) = sys.argv[1:]
root = Path(root_dir)
boundary = ParentRootSideEffectBoundary()
attestation = boundary.attest(
    ParentRootAttestationRequest(cwd=root, explicit_root=root, purpose="update-lifecycle")
)
binding = json.loads(Path(binding_path).read_text(encoding="utf-8"))
rebind = json.loads(Path(rebind_path).read_text(encoding="utf-8"))
packet = json.loads(Path(packet_path).read_text(encoding="utf-8"))
queue = materialize_queue_receipt(
    binding=binding,
    source_namespace=str(Path(source_namespace).resolve()),
    source_main_rebind_receipt_id=rebind["rebind_receipt_id"],
    source_main_readback_evidence_ref=readback_ref,
    publication_readback_receipt=packet["publication_readback_receipt"],
    state="accepted",
)
predecessors = [
    {
        "queue_number": 388,
        "source_pr": "#388",
        "publication_evidence_id": predecessor_388_ref,
    },
    {
        "queue_number": 389,
        "source_pr": "#389",
        "source_pr_sha": "3ce14a5e8103e3c53178d579be9cb7920c715ecb",
        "publication_evidence_id": predecessor_389_ref,
    },
]
frontier = materialize_dependency_frontier(
    binding=binding,
    queue_receipt=queue,
    rebind_receipt=rebind,
    source_main_readback_evidence_ref=readback_ref,
    ordered_predecessor_evidence=predecessors,
)

def persist_once(path_text, record, validator, identity_field):
    path = Path(path_text)
    if path.is_file():
        existing = validator(json.loads(path.read_text(encoding="utf-8")))
        validate_immutable_replay(existing, record, field=str(path))
        replay = json.loads(json.dumps(existing))
        replay["binding"]["timing"]["replayed"] = True
        return replay
    rendered = (json.dumps(record, indent=2, sort_keys=True) + "\n").encode("utf-8")
    boundary.write_parent_owned_file(attestation, path, rendered, "update-lifecycle")
    return record

queue_result = persist_once(
    queue_path, queue, validate_queue_receipt, "queue_receipt_id"
)
frontier_result = persist_once(
    frontier_path, frontier, validate_dependency_frontier, "frontier_id"
)
marker = {
    "schema": "agent-canon.update-lifecycle-current-transaction.v1",
    "transaction_id": binding["transaction_id"],
    "queue_receipt_id": queue_result["queue_receipt_id"],
    "frontier_id": frontier_result["frontier_id"],
}
marker_path = Path(current_marker_path)
if marker_path.is_file():
    existing_marker = json.loads(marker_path.read_text(encoding="utf-8"))
    if existing_marker != marker:
        raise SystemExit(f"input_identity_mismatch:{marker_path}")
else:
    boundary.write_parent_owned_file(
        attestation,
        marker_path,
        (json.dumps(marker, indent=2, sort_keys=True) + "\n").encode("utf-8"),
        "update-lifecycle",
    )
print(f"AGENT_CANON_QUEUE_RECEIPT_ID={queue_result['queue_receipt_id']}")
print(f"AGENT_CANON_QUEUE_REPLAYED={str(queue_result['binding']['timing']['replayed']).lower()}")
print(f"AGENT_CANON_FRONTIER_ID={frontier_result['frontier_id']}")
print(f"AGENT_CANON_FRONTIER_STATE={frontier_result['frontier_state']}")
PY
}

accept_dependency_frontier() {
  local pending_frontier_file="$1"
  local queue_receipt_file="$2"
  local rebind_receipt_file="$3"
  local acceptance_evidence_ref="$4"
  local source_main_sha="$5"
  local source_main_tree="$6"
  local accepted_output="${7:-$UPDATE_PROJECTION_DIR/frontier.accepted.json}"
  local g4_output="$UPDATE_EVIDENCE_DIR/g4.parent-projection-integrity.json"

  [[ "$source_main_sha" =~ ^[0-9a-f]{40}$ ]] \
    || die "accepted frontier requires exact origin/main readback identity"
  [[ "$source_main_tree" =~ ^[0-9a-f]{40}$ ]] \
    || die "accepted frontier requires exact origin/main tree readback identity"
  parent_ensure_dir "$UPDATE_STATE_DIR"
  parent_ensure_dir "$UPDATE_EVIDENCE_DIR"
  parent_ensure_dir "$UPDATE_PROJECTION_DIR"
  PYTHONPATH="$CANON_TOOLS_ROOT/agent_tools${PYTHONPATH:+:$PYTHONPATH}" \
    python3 - "$pending_frontier_file" "$queue_receipt_file" \
      "$rebind_receipt_file" "$source_main_sha" "$source_main_tree" \
      "$acceptance_evidence_ref" \
      "$accepted_output" "$SOURCE_PROJECTION_PACKET" "$g4_output" \
      "$PARENT_ROOT_DIR" "$ROOT_DIR" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

from parent_root_side_effects import (
    ParentRootAttestationRequest,
    ParentRootSideEffectBoundary,
)

from artifact_identity import canonical_json_bytes
from update_lifecycle_contract import (
    SourceMainReadbackIdentity,
    materialize_gate_verdict,
    validate_dependency_frontier,
    validate_dependency_frontier_transition,
    validate_gate_verdict,
    validate_immutable_replay,
    validate_source_projection_packet,
)

(
    pending_path,
    queue_path,
    rebind_path,
    source_main_sha,
    source_main_tree,
    acceptance_ref,
    output_path,
    packet_path,
    g4_path,
    parent_root_dir,
    logical_root_dir,
) = sys.argv[1:]
root = Path(parent_root_dir)
boundary = ParentRootSideEffectBoundary()
attestation = boundary.attest(
    ParentRootAttestationRequest(cwd=root, explicit_root=root, purpose="update-frontier")
)
pending = json.loads(Path(pending_path).read_text(encoding="utf-8"))
queue = json.loads(Path(queue_path).read_text(encoding="utf-8"))
rebind = json.loads(Path(rebind_path).read_text(encoding="utf-8"))
accepted = json.loads(json.dumps(pending))
accepted["frontier_state"] = "accepted"
accepted["preceding_frontier_evidence_id"] = pending["binding"]["evidence_ref"]
accepted["acceptance_evidence_ref"] = acceptance_ref
transaction_id = pending["binding"]["transaction_id"]
accepted = validate_dependency_frontier_transition(
    pending,
    accepted,
    queue_receipt=queue,
    rebind_receipt=rebind,
    origin_main_readback=SourceMainReadbackIdentity(
        commit_sha=source_main_sha,
        tree_sha=source_main_tree,
    ),
    ordered_oracle=[
        "source_pr:#388",
        "source_pr:#389",
        f"transaction:{transaction_id}",
    ],
)
path = Path(output_path)
if path.is_file():
    existing = validate_dependency_frontier(
        json.loads(path.read_text(encoding="utf-8"))
    )
    validate_immutable_replay(existing, accepted, field=str(path))
    result = json.loads(json.dumps(existing))
    result["binding"]["timing"]["replayed"] = True
else:
    boundary.write_parent_owned_file(
        attestation,
        path,
        (json.dumps(accepted, indent=2, sort_keys=True) + "\n").encode("utf-8"),
        "update-frontier",
    )
    result = accepted
packet = validate_source_projection_packet(
    json.loads(Path(packet_path).read_text(encoding="utf-8"))
)
g3 = packet["source_gate_verdicts"][2]

def immutable_receipt(record):
    value = json.loads(json.dumps(record))
    value["binding"].pop("timing", None)
    return value

g4 = materialize_gate_verdict(
    binding=result["binding"],
    gate_id="G4",
    ordered_input_evidence_refs=[
        g3["binding"]["evidence_ref"],
        queue["binding"]["evidence_ref"],
        result["acceptance_evidence_ref"],
    ],
    invariant="parent_projection_integrity",
    output_digest="sha256:"
    + hashlib.sha256(
        canonical_json_bytes(
            {
                "queue": immutable_receipt(queue),
                "frontier": immutable_receipt(result),
            }
        )
    ).hexdigest(),
    owner=str(Path(logical_root_dir).resolve())
    + "/tools/update_agent_canon.sh#accept_dependency_frontier",
    verdict="pass",
)
g4_output = Path(g4_path)
if g4_output.is_file():
    existing_g4 = validate_gate_verdict(
        json.loads(g4_output.read_text(encoding="utf-8"))
    )
    validate_immutable_replay(existing_g4, g4, field=str(g4_output))
    g4_result = json.loads(json.dumps(existing_g4))
    g4_result["binding"]["timing"]["replayed"] = True
else:
    boundary.write_parent_owned_file(
        attestation,
        g4_output,
        (json.dumps(g4, indent=2, sort_keys=True) + "\n").encode("utf-8"),
        "update-frontier",
    )
    g4_result = g4
print(f"AGENT_CANON_FRONTIER_ID={result['frontier_id']}")
print(f"AGENT_CANON_FRONTIER_STATE={result['frontier_state']}")
print(f"AGENT_CANON_FRONTIER_REPLAYED={str(result['binding']['timing']['replayed']).lower()}")
print(f"AGENT_CANON_SOURCE_MAIN_READBACK={source_main_sha}")
print(f"AGENT_CANON_G4_EVIDENCE_REF={g4_result['binding']['evidence_ref']}")
PY
}

advance_source_projection() {
  local packet="$SOURCE_PROJECTION_PACKET"
  local binding_file="$UPDATE_STATE_DIR/source-projection.binding.json"
  local rebind_file="$UPDATE_STATE_DIR/source-projection.rebind.json"
  local source_main_sha=""
  local source_main_tree=""
  local source_remote="origin"
  local projection_values=()

  [ -f "$packet" ] || die "source projection packet is missing"
  if [ "$AGENT_CANON_SOURCE_MODE" = "parent_projection" ]; then
    source_remote="$(submodule_remote_url)"
    [ -n "$source_remote" ] \
      || die "parent projection source remote is missing"
  fi
  source_main_sha="$(resolve_remote_branch_sha "$source_remote" main)"
  ensure_remote_commit_object "$AGENT_CANON_DIR" origin "$source_main_sha"
  source_main_tree="$(git -C "$AGENT_CANON_DIR" rev-parse "$source_main_sha^{tree}")"
  parent_ensure_dir "$UPDATE_STATE_DIR"
  parent_ensure_dir "$UPDATE_EVIDENCE_DIR"
  parent_ensure_dir "$UPDATE_PROJECTION_DIR"
  mapfile -t projection_values < <(
    PYTHONPATH="$CANON_TOOLS_ROOT/agent_tools${PYTHONPATH:+:$PYTHONPATH}" \
      python3 - "$packet" "$binding_file" "$rebind_file" \
        "$source_main_sha" "$source_main_tree" "$PARENT_ROOT_DIR" <<'PY'
import json
import sys
from pathlib import Path

from parent_root_side_effects import (
    ParentRootAttestationRequest,
    ParentRootSideEffectBoundary,
)

from update_lifecycle_contract import validate_source_projection_packet

(
    packet_path,
    binding_path,
    rebind_path,
    observed_source_main,
    observed_source_tree,
    root_dir,
) = sys.argv[1:]
root = Path(root_dir)
boundary = ParentRootSideEffectBoundary()
attestation = boundary.attest(
    ParentRootAttestationRequest(cwd=root, explicit_root=root, purpose="source-projection")
)
packet = validate_source_projection_packet(
    json.loads(Path(packet_path).read_text(encoding="utf-8"))
)
binding = packet["binding"]
publication = packet["publication_readback_receipt"]["pr_identity"]
if (
    publication["merge_commit_sha"] != observed_source_main
    or publication["merge_tree_sha"] != observed_source_tree
):
    raise SystemExit("frontier:origin_main_readback_mismatch")

def persist_projection(path_text, value):
    path = Path(path_text)
    rendered = json.dumps(value, indent=2, sort_keys=True) + "\n"
    if path.is_file():
        if path.read_text(encoding="utf-8") != rendered:
            raise SystemExit(f"input_identity_mismatch:{path}")
        return
    boundary.write_parent_owned_file(
        attestation, path, rendered.encode("utf-8"), "source-projection"
    )

persist_projection(binding_path, binding)
persist_projection(rebind_path, packet["source_main_rebind_receipt"])
readback = packet["publication_readback_receipt"]
predecessors = packet["ordered_predecessor_evidence"]
print(readback["publication_evidence_ref"])
print(predecessors[0]["publication_evidence_id"])
print(predecessors[1]["publication_evidence_id"])
print(packet["acceptance_evidence_ref"])
PY
  )
  [ "${#projection_values[@]}" -eq 4 ] \
    || die "source projection packet extraction failed"
  emit_queue_receipt \
    "$binding_file" \
    "$rebind_file" \
    "${projection_values[0]}" \
    "${projection_values[1]}" \
    "${projection_values[2]}" \
    "$packet"
  accept_dependency_frontier \
    "$UPDATE_PROJECTION_DIR/frontier.pending.json" \
    "$UPDATE_PROJECTION_DIR/queue.accepted.json" \
    "$rebind_file" \
    "${projection_values[3]}" \
    "$source_main_sha" \
    "$source_main_tree"
}

require_accepted_dependency_frontier() {
  if [ "$AGENT_CANON_SOURCE_MODE" = "parent_projection" ]; then
    ensure_source_projection_lifecycle
  fi
  local current_marker="$UPDATE_STATE_DIR/current-transaction"
  local accepted_queue="$UPDATE_PROJECTION_DIR/queue.accepted.json"
  local accepted_frontier="$UPDATE_PROJECTION_DIR/frontier.accepted.json"
  local g4_receipt="$UPDATE_EVIDENCE_DIR/g4.parent-projection-integrity.json"
  [ -f "$current_marker" ] \
    || die "parent projection blocked: current transaction marker is missing"
  [ -f "$accepted_queue" ] \
    || die "parent projection blocked until queue acceptance"
  [ -f "$accepted_frontier" ] \
    || die "parent projection blocked until dependency frontier acceptance"
  [ -f "$g4_receipt" ] \
    || die "parent projection blocked until G4 integrity evidence"
  PYTHONPATH="$CANON_TOOLS_ROOT/agent_tools${PYTHONPATH:+:$PYTHONPATH}" \
    python3 - "$accepted_frontier" "$accepted_queue" "$current_marker" \
      "$g4_receipt" <<'PY'
import json
import sys
from pathlib import Path
from update_lifecycle_contract import (
    binding_identity,
    validate_dependency_frontier,
    validate_gate_verdict,
    validate_queue_receipt,
)

frontier = validate_dependency_frontier(
    json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
)
queue = validate_queue_receipt(
    json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
)
marker = json.loads(Path(sys.argv[3]).read_text(encoding="utf-8"))
g4 = validate_gate_verdict(
    json.loads(Path(sys.argv[4]).read_text(encoding="utf-8"))
)
if set(marker) != {"schema", "transaction_id", "queue_receipt_id", "frontier_id"}:
    raise SystemExit("frontier:current_transaction_marker_invalid")
if marker["schema"] != "agent-canon.update-lifecycle-current-transaction.v1":
    raise SystemExit("frontier:current_transaction_marker_invalid")
if frontier["frontier_state"] != "accepted":
    raise SystemExit("frontier:not_accepted")
if frontier["binding"]["transaction_id"] != marker["transaction_id"]:
    raise SystemExit("frontier:transaction_identity_mismatch")
if frontier["frontier_id"] != marker["frontier_id"]:
    raise SystemExit("frontier:identity_mismatch")
if queue["state"] != "accepted" or queue["queue_receipt_id"] != marker["queue_receipt_id"]:
    raise SystemExit("frontier:queue_not_accepted")
if binding_identity(queue["binding"]) != binding_identity(frontier["binding"]):
    raise SystemExit("frontier:queue_identity_mismatch")
if (
    g4["gate_id"] != "G4"
    or g4["verdict"] != "pass"
    or binding_identity(g4["binding"]) != binding_identity(frontier["binding"])
    or frontier["acceptance_evidence_ref"]
    not in g4["ordered_input_evidence_refs"]
):
    raise SystemExit("frontier:g4_identity_mismatch")
print(f"AGENT_CANON_PARENT_PROJECTION_FRONTIER={frontier['frontier_id']}")
PY
}

cmd_plan() {
  local branch="${1:-$DEFAULT_BRANCH}"
  if [ "$AGENT_CANON_SOURCE_MODE" = "standalone_source" ]; then
    echo "agent_canon_plan_route=standalone_source_rebind"
    echo "agent_canon_plan_source_namespace=$AGENT_CANON_DIR"
    echo "agent_canon_plan_owner_namespace=$UPDATE_OWNER_NAMESPACE"
    echo "agent_canon_plan_branch=$branch"
    return
  fi
  run_parent_bound_sync plan "$branch"
}

cmd_latest() {
  local branch="${1:-$DEFAULT_BRANCH}"
  local plan_output=""
  local plan_rc=0
  local attach_rc=0
  local route=""
  local prefix_mode=""
  local dirty_update_surface=""
  local submodule_worktree_status=""
  local latest_log=""
  local latest_rc=0
  local todo_rc=0

  if [ "$AGENT_CANON_SOURCE_MODE" = "standalone_source" ]; then
    materialize_source_projection_handoff
    if [ -f "$SOURCE_PROJECTION_PACKET" ]; then
      advance_source_projection
      return
    fi
    cmd_merge_main_into_current "$branch"
    return
  fi

  attach_reconstructible_detached_parent_submodule "$branch" || attach_rc=$?
  if [ "$attach_rc" -ne 0 ]; then
    return "$attach_rc"
  fi

  plan_output="$(cmd_plan "$branch" 2>&1)" || plan_rc=$?
  printf '%s\n' "$plan_output"
  if [ "$plan_rc" -ne 0 ]; then
    return "$plan_rc"
  fi
  route="$(plan_value agent_canon_plan_route "$plan_output")"
  prefix_mode="$(plan_value agent_canon_plan_prefix_mode "$plan_output")"
  dirty_update_surface="$(plan_value agent_canon_plan_dirty_update_surface "$plan_output")"
  submodule_worktree_status="$(plan_value agent_canon_plan_submodule_worktree_status "$plan_output")"

  if [ "${route:-}" != "deferred_branch_pr" ]; then
    require_accepted_dependency_frontier
  fi

  if route_requires_agent_workflow "$route" "$prefix_mode"; then
    emit_agentcanon_conflict_workflow_route "route=${route:-unknown};dirty_update_surface=${dirty_update_surface:-unknown};submodule_worktree_status=${submodule_worktree_status:-unknown}"
    return 2
  fi

  latest_log_dir="$(parent_temp_dir "$CANON_PARENT_TMPDIR" latest-log)"
  latest_log="$latest_log_dir/output"
  local latest_output=""
  latest_output="$(run_parent_bound_sync ensure-latest "$branch" 2>&1)" || latest_rc=$?
  parent_write_file "$latest_log" "$latest_output"
  if [ "$latest_rc" -ne 0 ]; then
    cat "$latest_log"
    if grep -q '^agent_canon_materialization_collision=yes$' "$latest_log"; then
      emit_agentcanon_conflict_workflow_route "route=submodule_materialization_collision;ensure_latest_failed=$latest_rc"
    elif grep -q '^agent_canon_materialization_merge_conflict=yes$' "$latest_log"; then
      emit_agentcanon_conflict_workflow_route "route=submodule_merge_conflict;ensure_latest_failed=$latest_rc"
    else
      emit_agentcanon_conflict_workflow_route "ensure_latest_failed=$latest_rc;route=${route:-unknown}"
    fi
    parent_remove_file "$latest_log"
    return "$latest_rc"
  fi
  cat "$latest_log"
  if [ "$prefix_mode" = "submodule" ] && ! grep -q '^agent_canon_latest_submodule_local_state_checked=yes$' "$latest_log"; then
    parent_remove_file "$latest_log"
    emit_agentcanon_conflict_workflow_route "ensure_latest_missing_submodule_local_state_evidence=yes;route=${route:-unknown}"
    return 2
  fi
  if grep -q '^agent_canon_latest=deferred_branch_pr$' "$latest_log"; then
    parent_remove_file "$latest_log"
    echo "AGENT_CANON_LATEST_TOOL_RESULT=deferred_branch_pr"
    echo "NEXT_ACTION=after_agentcanon_PR_merge_rerun_make_agent-canon-ensure-latest"
    return 0
  fi
  parent_remove_file "$latest_log"

  run_parent_bound_sync check
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
  local attach_rc=0

  if [ "$AGENT_CANON_SOURCE_MODE" = "standalone_source" ]; then
    cmd_merge_main_into_current "$branch"
    return
  fi

  attach_reconstructible_detached_parent_submodule "$branch" || attach_rc=$?
  if [ "$attach_rc" -ne 0 ]; then
    return "$attach_rc"
  fi
  require_accepted_dependency_frontier

  latest_log_dir="$(parent_temp_dir "$CANON_PARENT_TMPDIR" latest-log)"
  latest_log="$latest_log_dir/output"
  local latest_output=""
  latest_output="$(run_parent_bound_sync ensure-latest "$branch" 2>&1)" || latest_rc=$?
  parent_write_file "$latest_log" "$latest_output"
  cat "$latest_log"
  if [ "$latest_rc" -ne 0 ]; then
    parent_remove_file "$latest_log"
    return "$latest_rc"
  fi
  if grep -q '^agent_canon_latest=deferred_branch_pr$' "$latest_log"; then
    parent_remove_file "$latest_log"
    echo "AGENT_CANON_TOOL_REBUILD=skipped_deferred_branch_pr"
    return 0
  fi
  parent_remove_file "$latest_log"
  rebuild_agent_tools_if_available
}

cmd_rebuild_tools() {
  rebuild_agent_tools_if_available
}

cmd_status() {
  if [ "$AGENT_CANON_SOURCE_MODE" = "standalone_source" ]; then
    echo "agent_canon_source_mode=standalone_source"
    echo "agent_canon_source_namespace=$AGENT_CANON_DIR"
    echo "agent_canon_source_head=$(git -C "$AGENT_CANON_DIR" rev-parse HEAD)"
    echo "agent_canon_source_tree=$(git -C "$AGENT_CANON_DIR" rev-parse HEAD^{tree})"
    echo "agent_canon_source_worktree_status=$(git -C "$AGENT_CANON_DIR" status --porcelain=v1 --untracked-files=all | wc -l | tr -d ' ')"
    return
  fi
  run_parent_bound_sync status
}

cmd_merge_main_into_current() {
  local branch="${1:-$DEFAULT_BRANCH}"
  local remote_url=""
  local remote_sha=""
  local pre_head=""
  local post_head=""
  local current_branch=""
  local submodule_status=""
  local collision_path=""
  local collision_rc=0
  local materialization_result_tree=""
  local materialization_result_tree_rc=0
  local merge_log=""
  local result=""
  local conflict_files=""

  ensure_agent_canon_submodule
  remote_url="$(submodule_remote_url)"
  [ -n "$remote_url" ] || die "submodule '$PREFIX' has no .gitmodules url"

  remote_sha="$(resolve_remote_branch_sha "$remote_url" "$branch")"
  ensure_remote_commit_object "$AGENT_CANON_DIR" "$remote_url" "$remote_sha"
  pre_head="$(git -C "$AGENT_CANON_DIR" rev-parse HEAD)"
  current_branch="$(git -C "$AGENT_CANON_DIR" symbolic-ref --quiet --short HEAD 2>/dev/null || true)"
  submodule_status="$(git -C "$AGENT_CANON_DIR" status --short --untracked-files=all)"

  echo "agent_canon_merge_prefix=$PREFIX"
  echo "agent_canon_merge_source=${remote_url}#${branch}"
  echo "agent_canon_merge_source_sha=$remote_sha"
  echo "agent_canon_merge_target_branch=${current_branch:-<detached>}"
  echo "agent_canon_merge_pre_head=$pre_head"

  echo "agent_canon_merge_worktree_status=$([ -n "$submodule_status" ] && echo dirty || echo clean)"
  echo "agent_canon_merge_acceptance_predicate=materialization_merge_conflict_or_unpreservable_materialization_collision"

  if [ -z "$current_branch" ]; then
    echo "agent_canon_merge_result=blocked_detached_head"
    echo "agent_canon_parent_pin_pending=$(parent_pin_pending "$pre_head")"
    echo "NEXT_ACTION=request_user_direction_preserve_current_checkout_then_rerun_with_inline_git_authority_and_reason"
    die "submodule '$PREFIX' is detached; create or switch to a branch before merging main"
  fi
  if update_materialization_unresolved_conflict "$AGENT_CANON_DIR"; then
    echo "agent_canon_merge_unresolved_merge_conflict=yes"
    echo "agent_canon_merge_merge_conflict=yes"
    echo "agent_canon_merge_conflict_type=existing_unresolved_index"
    echo "agent_canon_merge_result=blocked_unresolved_merge_conflict"
    echo "NEXT_ACTION=resolve_agentcanon_merge_conflicts_then_rerun_merge-main-into-current"
    die "current AgentCanon branch has unresolved merge conflicts"
  fi
  materialization_result_tree="$(
    update_materialization_result_tree "$AGENT_CANON_DIR" "$pre_head" "$remote_sha"
  )" || materialization_result_tree_rc=$?
  if [ "$materialization_result_tree_rc" -eq 2 ]; then
    echo "agent_canon_merge_unresolved_merge_conflict=no"
    echo "agent_canon_merge_merge_conflict=yes"
    echo "agent_canon_merge_conflict_type=virtual_merge_result"
    echo "agent_canon_merge_result=blocked_merge_conflict"
    echo "NEXT_ACTION=resolve_committed_branch_merge_conflict_then_rerun_merge-main-into-current"
    die "current AgentCanon branch conflicts with the virtual merge result"
  fi
  [ "$materialization_result_tree_rc" -eq 0 ] \
    || die "failed to compute the AgentCanon virtual merge result tree"
  echo "agent_canon_merge_unresolved_merge_conflict=no"
  echo "agent_canon_merge_merge_conflict=no"
  echo "agent_canon_merge_conflict_type=none"
  collision_path="$(
    update_materialization_collision_path \
      "$AGENT_CANON_DIR" "$pre_head" "$materialization_result_tree"
  )" || collision_rc=$?
  if [ "$collision_rc" -eq 0 ]; then
    echo "agent_canon_merge_materialization_collision=yes"
    printf 'agent_canon_merge_materialization_collision_path=%q\n' "$collision_path"
    echo "agent_canon_merge_result=blocked_unpreservable_collision"
    echo "NEXT_ACTION=materialize_or_move_the_colliding_local_path_then_rerun_merge-main-into-current"
    die "current AgentCanon branch has a local materialized path in the exact update write set"
  fi
  [ "$collision_rc" -eq 1 ] \
    || die "failed to compute the AgentCanon materialization collision set"
  echo "agent_canon_merge_materialization_collision=no"

  if [ "$pre_head" = "$remote_sha" ]; then
    echo "agent_canon_merge_post_head=$pre_head"
    emit_remote_main_ancestor_evidence "$remote_sha" "$pre_head"
    echo "agent_canon_merge_result=already_current"
    echo "agent_canon_parent_pin_pending=$(parent_pin_pending "$pre_head")"
    echo "NEXT_ACTION=continue_parent_workflow"
    return
  fi

  if git -C "$AGENT_CANON_DIR" merge-base --is-ancestor "$remote_sha" "$pre_head"; then
    echo "agent_canon_merge_post_head=$pre_head"
    emit_remote_main_ancestor_evidence "$remote_sha" "$pre_head"
    echo "agent_canon_merge_result=already_contains_main"
    echo "agent_canon_parent_pin_pending=$(parent_pin_pending "$pre_head")"
    echo "NEXT_ACTION=push_current_agentcanon_branch_and_open_or_update_PR"
    return
  fi

  merge_log_dir="$(parent_temp_dir "$CANON_PARENT_TMPDIR" merge-log)"
  merge_log="$merge_log_dir/output"
  local merge_output=""
  if merge_output="$(git -C "$AGENT_CANON_DIR" merge --no-autostash --no-edit "$remote_sha" 2>&1)"; then
    parent_write_file "$merge_log" "$merge_output"
    post_head="$(git -C "$AGENT_CANON_DIR" rev-parse HEAD)"
    if git -C "$AGENT_CANON_DIR" merge-base --is-ancestor "$pre_head" "$remote_sha"; then
      result="fast_forwarded"
    else
      result="merged"
    fi
    parent_remove_file "$merge_log"
    echo "agent_canon_merge_post_head=$post_head"
    emit_remote_main_ancestor_evidence "$remote_sha" "$post_head"
    echo "agent_canon_merge_result=$result"
    echo "agent_canon_merge_local_changes=$([ -n "$submodule_status" ] && echo preserved || echo none)"
    echo "agent_canon_parent_pin_pending=$(parent_pin_pending "$post_head")"
    echo "NEXT_ACTION=run_validation_then_push_current_agentcanon_branch_and_open_or_update_PR"
    return
  fi

  parent_write_file "$merge_log" "$merge_output"
  cat "$merge_log" >&2
  parent_remove_file "$merge_log"
  conflict_files="$(git -C "$AGENT_CANON_DIR" diff --name-only --diff-filter=U | paste -sd, -)"
  echo "agent_canon_merge_unresolved_merge_conflict=$([ -n "$conflict_files" ] && echo yes || echo no)"
  echo "agent_canon_merge_result=$([ -n "$conflict_files" ] && echo blocked_unresolved_merge_conflict || echo failed_without_conflict)"
  echo "agent_canon_merge_conflict_files=${conflict_files:-<unset>}"
  echo "agent_canon_parent_pin_pending=$(parent_pin_pending "$pre_head")"
  echo "NEXT_ACTION=resolve_agentcanon_merge_conflicts_then_commit_and_push_current_branch"
  return 1
}

main() {
  local subcommand="${1:-}"
  case "$subcommand" in
    latest|apply|merge-main-into-current)
      require_commit_provenance "$subcommand"
      ;;
  esac
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
