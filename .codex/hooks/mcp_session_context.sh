#!/usr/bin/env bash
# @dependency-start
# responsibility Runs mcp session context shell automation.
# upstream implementation ../hooks.json invokes this hook for SessionStart
# upstream implementation ../config.toml enables hooks
# upstream design ../README.md documents MCP inventory preflight
# downstream implementation ../../tests/agent_tools/test_codex_hooks.py validates output JSON
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
    "additionalContext": "Repo MCP requirement: ordinary consultation, brainstorming, routing-only advice, and explanation-only turns are not repository tasks. Do not run check_mcp_inventory.py, repo MCP tools, shell commands, or GitHub checks for those turns unless the user asks to inspect repo state, edit files, run validation, process PRs, or otherwise execute repository work. When a repository task starts, confirm repo_mcp_server in configured Codex inventory with 'python3 tools/agent_tools/check_mcp_inventory.py --require repo_mcp_server' even when the user did not mention MCP. When it passes, prefer repo MCP tools for repo root/status, goal.loop_status, goal.plan, and MCP-covered context checks. In adaptive-improvement-loop work, goal.loop_status is the mechanical iteration gate: NEXT_ACTION=run_next_iteration means continue the next backlog iteration and do not return completion; goal.plan is the mechanical next-slice work-unit surface when available. Current repo_mcp_server is context/loop-status only, not a file-edit tool; do not repeat that limitation in every user update unless MCP failure/mismatch affects the work or the user asks about editing mode. The canonical launcher is '.codex/config.toml' -> 'bash mcp/repo_mcp_server.sh'; do not silently replace it with an ad hoc local process. If it is missing or startup fails during repository work, repair '.codex/', 'mcp/', or base command availability before continuing."
  }
}
JSON
