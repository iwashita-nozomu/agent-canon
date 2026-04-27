#!/usr/bin/env bash
# @dependency-start
# upstream design README.md MCP runtime surface contract
# upstream implementation ../.codex/config.toml invokes this repo-local launcher
# downstream implementation ./repo_mcp_server.py implements the stdio MCP server
# @dependency-end

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "${SCRIPT_DIR}/repo_mcp_server.py"
