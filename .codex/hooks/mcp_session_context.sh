#!/usr/bin/env bash
# @dependency-start
# responsibility Emits optional MCP session context shell automation.
# upstream design ../README.md documents MCP inventory preflight policy
# upstream implementation ../config.toml enables hooks
# downstream implementation ../../tests/agent_tools/test_codex_hooks.py validates optional context JSON
# @dependency-end
set -euo pipefail

event="${1:-SessionStart}"
case "${event}" in
  SessionStart) ;;
  *) event="SessionStart" ;;
esac

cat <<JSON
{
  "hookSpecificOutput": {
    "hookEventName": "${event}",
    "additionalContext": "Repo MCP note: ordinary consultation, brainstorming, routing-only advice, explanation-only turns, and GitHub-only read inspection are not repository tasks. Do not run check_mcp_inventory.py, repo MCP tools, shell commands, or GitHub checks for those turns unless the user asks to inspect local repo state, edit files, run validation, mutate PRs/issues, run local CI, or execute implementation work. AgentCanon no longer installs this script as a SessionStart hook; it is a manual context helper only. When classification is unclear or the task changes MCP surfaces, use 'agent-canon mcp-preflight-policy --request-kind <kind>'; github-actions-read/github-read/pr-read/issue-read return skip, while repo-read/implementation/validation/pr-mutation/issue-sync return required. Use 'agent-canon mcp-inventory --root . --require repo_mcp_server --session-cache' or 'python3 tools/agent_tools/check_mcp_inventory.py --require repo_mcp_server --report-dir <run>' only when the workflow explicitly needs MCP evidence or the task edits '.codex/config.toml', 'mcp/', repo MCP tools, or MCP-dependent goal-loop gates. If the Rust CLI or local Cargo cannot read AgentCanon lockfiles, record mcp_preflight_unavailable=<reason> and continue with Python/shell validation unless the task depends on MCP runtime behavior. When MCP passes, prefer repo MCP tools for repo root/status, goal.loop_status, goal.plan, and MCP-covered context checks. In adaptive-improvement-loop work, goal.loop_status is the mechanical iteration gate: NEXT_ACTION=run_next_iteration means continue the next backlog iteration and do not return completion; goal.plan is the mechanical next-slice work-unit surface when available. Current repo_mcp_server is context/loop-status only, not a file-edit tool; do not repeat that limitation in every user update unless MCP failure/mismatch affects the work or the user asks about editing mode. The canonical launcher is '.codex/config.toml' -> 'bash mcp/repo_mcp_server.sh'; do not silently replace it with an ad hoc local process."
  }
}
JSON
