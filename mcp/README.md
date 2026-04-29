<!--
@dependency-start
responsibility Documents MCP Runtime Surface for this repository.
upstream implementation ../.codex/config.toml declares repo-local MCP launcher
downstream implementation ./repo_mcp_server.sh starts the stdio server
downstream implementation ./repo_mcp_server.py implements the stdio server
@dependency-end
-->

# MCP Runtime Surface

This directory is the shared Agent Canon MCP runtime surface.

The template root exposes it as `mcp/` through `tools/sync_agent_canon.sh link-root`.
Codex starts `repo_mcp_server` through the repo-local launcher:

```bash
bash mcp/repo_mcp_server.sh
```

Do not require a host-global `repo_mcp_server` executable.
