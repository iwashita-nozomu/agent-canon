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

The Codex server config pins `cwd = "."`, and the launcher exports
`CODEX_WORKSPACE_ROOT` from the repo-local `mcp/` path before starting Python.
This keeps goal/resume cycles from restarting the stdio server against a stale
or non-root working directory.

## Ownership Boundary

AgentCanon owns the repo MCP implementation:

- `mcp/repo_mcp_server.sh`
- `mcp/repo_mcp_server.py`
- the tool contract listed in this document

Template and derived repositories expose that implementation as the root
`mcp/` runtime view. Fix the implementation in `vendor/agent-canon/mcp/` and
repair the root view with `bash tools/sync_agent_canon.sh link-root`.

Codex owns registration and runtime wiring:

- `.codex/config.toml` registers `[mcp_servers.repo_mcp_server]`
- `.codex/hooks.json` and `.codex/hooks/` inject MCP preflight context
- user-level Codex trust, profiles, apps, and external connectors decide which
  runtime tools are available in a session

Do not merge these owner surfaces. The AgentCanon repo MCP server provides
repo context and goal-loop checks only. It is not the file-edit surface, GitHub
connector, shell runner, web browser, or a replacement for Codex-provided apps.
If Codex already provides a runtime tool or connector, do not reimplement that
capability in `repo_mcp_server`.

## Tools

- `repo.root`: returns the repository root.
- `repo.status`: returns `git status --short --branch --untracked-files=all`.
- `goal.loop_status`: runs `tools/agent_tools/goal_loop.py status` for `goal.md`
  and returns `GOAL_LOOP_STATUS` plus `NEXT_ACTION`. The adaptive improvement
  loop uses this tool as the mechanical iteration gate:
  `NEXT_ACTION=run_next_iteration`
  means continue the next backlog item, not completion.
- `goal.plan`: runs `tools/agent_tools/goal_loop.py plan` for `goal.md` and
  returns the next implementation-ready slice for goal-loop planning.
  When Codex `goals` is enabled, this MCP tool remains the repo-level gate;
  Codex goals is only the session view of the same `goal.md` contract.
