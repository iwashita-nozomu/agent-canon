#!/usr/bin/env bash
# @dependency-start
# contract tool
# responsibility Checks agent canon latest CI readiness.
# upstream design ../README.md shared automation index
# upstream design ../../agents/workflows/agent-canon-pr-workflow.md defines PR-first propagation after dirty shared-canon checks
# upstream design ../../agents/workflows/derived-agent-canon-diff-workflow.md defines branch route for derived shared-canon diffs
# @dependency-end

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"
PREFIX="${AGENT_CANON_PREFIX:-vendor/agent-canon}"

plan_output="$(bash tools/update_agent_canon.sh plan)"
printf '%s\n' "$plan_output"

route="$(printf '%s\n' "$plan_output" | awk -F= '/^agent_canon_plan_route=/{print $2}')"
dirty_worktree="$(printf '%s\n' "$plan_output" | awk -F= '/^agent_canon_plan_dirty_worktree=/{print $2}')"
dirty_update_surface="$(printf '%s\n' "$plan_output" | awk -F= '/^agent_canon_plan_dirty_update_surface=/{print $2}')"
prefix_mode="$(printf '%s\n' "$plan_output" | awk -F= '/^agent_canon_plan_prefix_mode=/{print $2}')"
remote_sha="$(printf '%s\n' "$plan_output" | awk -F= '/^agent_canon_plan_remote_sha=/{print $2}')"
submodule_worktree_head="$(printf '%s\n' "$plan_output" | awk -F= '/^agent_canon_plan_submodule_worktree_head=/{print $2}')"
submodule_worktree_status="$(printf '%s\n' "$plan_output" | awk -F= '/^agent_canon_plan_submodule_worktree_status=/{print $2}')"
submodule_parent_pin_remote_match="$(printf '%s\n' "$plan_output" | awk -F= '/^agent_canon_plan_submodule_parent_pin_remote_match=/{print $2}')"
submodule_worktree_remote_match="$(printf '%s\n' "$plan_output" | awk -F= '/^agent_canon_plan_submodule_worktree_remote_match=/{print $2}')"
submodule_worktree_clean="not_applicable"
if [[ "${prefix_mode:-}" == "submodule" ]]; then
  if [[ "${submodule_worktree_status:-}" == "clean" ]]; then
    submodule_worktree_clean="yes"
  elif [[ "${submodule_worktree_status:-}" == "dirty" ]]; then
    submodule_worktree_clean="no"
  fi
fi

emit_submodule_worktree_evidence() {
  if [[ "${prefix_mode:-}" != "submodule" ]]; then
    return
  fi
  echo "AGENT_CANON_LATEST_SUBMODULE_WORKTREE_HEAD=${submodule_worktree_head}"
  echo "AGENT_CANON_LATEST_SUBMODULE_WORKTREE_CLEAN=${submodule_worktree_clean}"
  echo "AGENT_CANON_LATEST_SUBMODULE_WORKTREE_REMOTE_MATCH=${submodule_worktree_remote_match}"
  echo "AGENT_CANON_LATEST_SUBMODULE_PARENT_PIN_REMOTE_MATCH=${submodule_parent_pin_remote_match:-unavailable}"
}

case "$route" in
  already_current_tree|already_current_split|already_current_submodule)
    if [[ "${dirty_update_surface:-}" == "yes" && "${submodule_worktree_remote_match}" != "yes" ]]; then
      echo "AGENT_CANON_LATEST=fail"
      echo "AGENT_CANON_LATEST_ROUTE=${route:-unknown}"
      emit_submodule_worktree_evidence
      echo "AGENT_CANON_LATEST_WORKFLOW=agents/workflows/derived-agent-canon-diff-workflow.md"
      echo "AGENT_CANON_LATEST_NEXT_ACTION=commit_agentcanon_branch_then_open_agent-canon_PR_then_after_merge_run_make_agent-canon-ensure-latest"
      echo "AGENT_CANON_LATEST_MERGE_COMMAND=bash tools/update_agent_canon.sh merge-main-into-current-preserve-dirty"
      echo "AgentCanon update surface is dirty; commit the AgentCanon branch, merge GitHub main into it, and open an AgentCanon PR before treating the latest gate as clean." >&2
      exit 1
    fi
    echo "AGENT_CANON_LATEST=pass"
    echo "AGENT_CANON_LATEST_ROUTE=${route:-unknown}"
    emit_submodule_worktree_evidence
    ;;
  deferred_branch_pr)
    echo "AGENT_CANON_LATEST=pass"
    echo "AGENT_CANON_LATEST_ROUTE=${route:-unknown}"
    emit_submodule_worktree_evidence
    echo "AGENT_CANON_LATEST_GATE=deferred_branch_pr"
    echo "AGENT_CANON_LATEST_NEXT_ACTION=after_agentcanon_PR_merge_rerun_make_agent-canon-ensure-latest"
    echo "AgentCanon parent pin is a clean pushed branch head ahead of remote main; treating latest as deferred to the AgentCanon PR workflow." >&2
    ;;
  local_contains_remote)
    echo "AGENT_CANON_LATEST=fail"
    echo "AGENT_CANON_LATEST_ROUTE=${route:-unknown}"
    emit_submodule_worktree_evidence
    echo "AGENT_CANON_LATEST_WORKFLOW=agents/workflows/derived-agent-canon-diff-workflow.md"
    echo "AGENT_CANON_LATEST_NEXT_ACTION=commit_agentcanon_branch_then_open_agent-canon_PR_then_after_merge_run_make_agent-canon-ensure-latest"
    echo "AGENT_CANON_LATEST_MERGE_COMMAND=bash tools/update_agent_canon.sh merge-main-into-current-preserve-dirty"
    echo "AgentCanon parent pin contains local shared-canon commits; route them through an AgentCanon branch and PR before treating the parent repository as latest." >&2
    exit 1
    ;;
  *)
    if [[ "${prefix_mode:-}" == "submodule" && "${submodule_worktree_remote_match}" == "yes" && "${submodule_worktree_clean}" == "yes" ]]; then
      echo "AGENT_CANON_LATEST=pass"
      echo "AGENT_CANON_LATEST_ROUTE=${route:-unknown}"
      emit_submodule_worktree_evidence
      echo "AGENT_CANON_LATEST_PARENT_PIN_PENDING=yes"
      echo "AGENT_CANON_LATEST_AUTO_REPAIR=skipped_read_only_check"
      echo "AGENT_CANON_LATEST_NEXT_ACTION=run_make_agent-canon-ensure-latest_then_commit_updated_submodule_pin"
      echo "AgentCanon submodule worktree is clean and already at remote main; run 'make agent-canon-ensure-latest' to stage the parent gitlink pin." >&2
      exit 0
    fi
    if [[ "${prefix_mode:-}" == "submodule" && "${submodule_worktree_remote_match}" == "yes" ]]; then
      echo "AGENT_CANON_LATEST=fail"
      echo "AGENT_CANON_LATEST_ROUTE=${route:-unknown}"
      emit_submodule_worktree_evidence
      echo "AGENT_CANON_LATEST_PARENT_PIN_PENDING=yes"
      echo "AGENT_CANON_LATEST_NEXT_ACTION=repair_submodule_worktree_then_rerun"
      echo "AgentCanon submodule worktree points at remote main but has local dirt; repair the submodule worktree before staging the parent gitlink pin." >&2
      exit 1
    fi
    echo "AGENT_CANON_LATEST=fail"
    echo "AGENT_CANON_LATEST_ROUTE=${route:-unknown}"
    emit_submodule_worktree_evidence
    if [[ "${dirty_update_surface:-${dirty_worktree:-}}" == "yes" && "${prefix_mode:-}" == "submodule" ]]; then
      echo "AGENT_CANON_LATEST_WORKFLOW=agents/workflows/derived-agent-canon-diff-workflow.md"
      echo "AGENT_CANON_LATEST_NEXT_ACTION=commit_agentcanon_branch_then_open_agent-canon_PR_then_after_merge_run_make_agent-canon-ensure-latest"
      echo "AGENT_CANON_LATEST_MERGE_COMMAND=bash tools/update_agent_canon.sh merge-main-into-current-preserve-dirty"
      echo "AGENT_CANON_LATEST_POST_MERGE_COMMAND=make agent-canon-ensure-latest"
      echo "Route shared-canon local changes through an AgentCanon branch and PR, merge GitHub main into the branch first, then rerun 'make agent-canon-ensure-latest' to bring the pin back." >&2
    elif [[ "${dirty_worktree:-}" == "yes" && "${prefix_mode:-}" == "submodule" ]]; then
      echo "AGENT_CANON_LATEST_WORKFLOW=agents/workflows/agent-canon-pr-workflow.md"
      echo "AGENT_CANON_LATEST_NEXT_ACTION=run_make_agent-canon-ensure-latest_parent_dirty_outside_update_surface_ok"
      echo "Parent worktree has unrelated dirty paths, but the AgentCanon update surface is clean; run 'make agent-canon-ensure-latest' before rerunning CI." >&2
    else
      echo "AGENT_CANON_LATEST_WORKFLOW=agents/workflows/agent-canon-pr-workflow.md"
      echo "AGENT_CANON_LATEST_NEXT_ACTION=run_make_agent-canon-ensure-latest_or_merge_agent-canon_PR_first"
      echo "Run 'make agent-canon-ensure-latest' after cleaning the worktree, or merge the shared-canon changes upstream first." >&2
    fi
    exit 1
    ;;
esac
