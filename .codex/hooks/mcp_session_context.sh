#!/usr/bin/env bash
# @dependency-start
# responsibility Runs mcp session context shell automation.
# upstream implementation ../hooks.json invokes this hook for SessionStart and UserPromptSubmit
# upstream implementation ../config.toml enables codex_hooks
# upstream design ../README.md documents MCP inventory preflight
# downstream implementation ../../tests/agent_tools/test_codex_hooks.py validates output JSON
# @dependency-end
set -euo pipefail

event="${1:-SessionStart}"
case "${event}" in
  SessionStart|UserPromptSubmit) ;;
  *) event="SessionStart" ;;
esac

cat <<JSON
{
  "hookSpecificOutput": {
    "hookEventName": "${event}",
    "additionalContext": "Repo MCP requirement: for repository tasks, confirm repo_mcp_server in configured Codex inventory with 'python3 tools/agent_tools/check_mcp_inventory.py --require repo_mcp_server' even when the user did not mention MCP. When it passes, prefer repo MCP tools for repo root/status and MCP-covered context checks. Current repo_mcp_server is status/context only, not a file-edit tool; do not repeat that limitation in every user update unless MCP failure/mismatch affects the work or the user asks about editing mode. The canonical launcher is '.codex/config.toml' -> 'bash mcp/repo_mcp_server.sh'; do not silently replace it with an ad hoc local process. If it is missing or startup fails, repair '.codex/', 'mcp/', or base command availability before continuing."
  }
}
JSON
