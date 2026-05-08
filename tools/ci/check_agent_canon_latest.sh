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
prefix_mode="$(printf '%s\n' "$plan_output" | awk -F= '/^agent_canon_plan_prefix_mode=/{print $2}')"

case "$route" in
  already_current_tree|already_current_split|already_current_submodule|local_contains_remote)
    echo "AGENT_CANON_LATEST=pass"
    ;;
  *)
    echo "AGENT_CANON_LATEST=fail"
    echo "AGENT_CANON_LATEST_ROUTE=${route:-unknown}"
    if [[ "${dirty_worktree:-}" == "yes" && "${prefix_mode:-}" == "submodule" ]]; then
      echo "AGENT_CANON_LATEST_WORKFLOW=agents/workflows/derived-agent-canon-diff-workflow.md"
      echo "AGENT_CANON_LATEST_NEXT_ACTION=commit_or_push_proposal_then_open_agent-canon_PR_then_after_merge_run_make_agent-canon-ensure-latest"
      echo "AGENT_CANON_LATEST_PROPOSAL_COMMAND=bash tools/update_agent_canon.sh push-proposal"
      echo "AGENT_CANON_LATEST_POST_MERGE_COMMAND=make agent-canon-ensure-latest"
      echo "Route shared-canon local changes through a proposal or AgentCanon PR, merge upstream first, then rerun 'make agent-canon-ensure-latest' to bring the pin back." >&2
    else
      echo "AGENT_CANON_LATEST_WORKFLOW=agents/workflows/agent-canon-pr-workflow.md"
      echo "AGENT_CANON_LATEST_NEXT_ACTION=run_make_agent-canon-ensure-latest_or_merge_agent-canon_PR_first"
      echo "Run 'make agent-canon-ensure-latest' after cleaning the worktree, or merge the shared-canon changes upstream first." >&2
    fi
    exit 1
    ;;
esac
