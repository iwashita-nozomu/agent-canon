#!/usr/bin/env bash
# @dependency-start
# responsibility Checks agent canon latest CI readiness.
# upstream design ../README.md shared automation index
# upstream design ../../agents/workflows/agent-canon-pr-workflow.md defines PR-first propagation after dirty shared-canon checks
# upstream design ../../agents/workflows/derived-agent-canon-diff-workflow.md defines proposal route for derived shared-canon diffs
# @dependency-end

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

plan_output="$(bash tools/update_agent_canon.sh plan)"
printf '%s\n' "$plan_output"

route="$(printf '%s\n' "$plan_output" | awk -F= '/^agent_canon_plan_route=/{print $2}')"
dirty_worktree="$(printf '%s\n' "$plan_output" | awk -F= '/^agent_canon_plan_dirty_worktree=/{print $2}')"
dirty_update_surface="$(printf '%s\n' "$plan_output" | awk -F= '/^agent_canon_plan_dirty_update_surface=/{print $2}')"
prefix_mode="$(printf '%s\n' "$plan_output" | awk -F= '/^agent_canon_plan_prefix_mode=/{print $2}')"
remote_sha="$(printf '%s\n' "$plan_output" | awk -F= '/^agent_canon_plan_remote_sha=/{print $2}')"
submodule_path="vendor/agent-canon"
submodule_worktree_head="<unavailable>"
submodule_worktree_clean="not_applicable"
submodule_worktree_remote_match="no"

if [[ "${prefix_mode:-}" == "submodule" && ( -d "${submodule_path}/.git" || -f "${submodule_path}/.git" ) ]]; then
  if submodule_worktree_head="$(git -C "${submodule_path}" rev-parse HEAD 2>/dev/null)"; then
    if [[ -z "$(git -C "${submodule_path}" status --short --untracked-files=all)" ]]; then
      submodule_worktree_clean="yes"
    else
      submodule_worktree_clean="no"
    fi
    if [[ "${submodule_worktree_clean}" == "yes" && -n "${remote_sha:-}" && "${remote_sha}" != "<unavailable>" && "${submodule_worktree_head}" == "${remote_sha}" ]]; then
      submodule_worktree_remote_match="yes"
    fi
  fi
fi

emit_submodule_worktree_evidence() {
  if [[ "${prefix_mode:-}" != "submodule" ]]; then
    return
  fi
  echo "AGENT_CANON_LATEST_SUBMODULE_WORKTREE_HEAD=${submodule_worktree_head}"
  echo "AGENT_CANON_LATEST_SUBMODULE_WORKTREE_CLEAN=${submodule_worktree_clean}"
  echo "AGENT_CANON_LATEST_SUBMODULE_WORKTREE_REMOTE_MATCH=${submodule_worktree_remote_match}"
}

case "$route" in
  already_current_tree|already_current_split|already_current_submodule|local_contains_remote)
    if [[ "${dirty_update_surface:-}" == "yes" && "${submodule_worktree_remote_match}" != "yes" ]]; then
      echo "AGENT_CANON_LATEST=fail"
      echo "AGENT_CANON_LATEST_ROUTE=${route:-unknown}"
      emit_submodule_worktree_evidence
      echo "AGENT_CANON_LATEST_WORKFLOW=agents/workflows/derived-agent-canon-diff-workflow.md"
      echo "AGENT_CANON_LATEST_NEXT_ACTION=commit_or_push_proposal_then_open_agent-canon_PR_then_after_merge_run_make_agent-canon-ensure-latest"
      echo "AGENT_CANON_LATEST_PROPOSAL_COMMAND=bash tools/update_agent_canon.sh push-proposal"
      echo "AgentCanon update surface is dirty; commit/push proposal or merge AgentCanon changes before treating the latest gate as clean." >&2
      exit 1
    fi
    echo "AGENT_CANON_LATEST=pass"
    echo "AGENT_CANON_LATEST_ROUTE=${route:-unknown}"
    emit_submodule_worktree_evidence
    ;;
  *)
    if [[ "${prefix_mode:-}" == "submodule" && "${submodule_worktree_remote_match}" == "yes" ]]; then
      echo "AGENT_CANON_LATEST=pass"
      echo "AGENT_CANON_LATEST_ROUTE=${route:-unknown}"
      emit_submodule_worktree_evidence
      echo "AGENT_CANON_LATEST_PARENT_PIN_PENDING=yes"
      echo "AGENT_CANON_LATEST_NEXT_ACTION=commit_updated_submodule_pin"
      echo "AgentCanon submodule worktree is clean and already at remote main; commit the parent gitlink pin before pushing the parent repository." >&2
      exit 0
    fi
    echo "AGENT_CANON_LATEST=fail"
    echo "AGENT_CANON_LATEST_ROUTE=${route:-unknown}"
    emit_submodule_worktree_evidence
    if [[ "${dirty_update_surface:-${dirty_worktree:-}}" == "yes" && "${prefix_mode:-}" == "submodule" ]]; then
      echo "AGENT_CANON_LATEST_WORKFLOW=agents/workflows/derived-agent-canon-diff-workflow.md"
      echo "AGENT_CANON_LATEST_NEXT_ACTION=commit_or_push_proposal_then_open_agent-canon_PR_then_after_merge_run_make_agent-canon-ensure-latest"
      echo "AGENT_CANON_LATEST_PROPOSAL_COMMAND=bash tools/update_agent_canon.sh push-proposal"
      echo "AGENT_CANON_LATEST_POST_MERGE_COMMAND=make agent-canon-ensure-latest"
      echo "Route shared-canon local changes through a proposal or AgentCanon PR, merge upstream first, then rerun 'make agent-canon-ensure-latest' to bring the pin back." >&2
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
