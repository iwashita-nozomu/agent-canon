<!--
@dependency-start
responsibility Documents MCP preflight and fallback policy for AgentCanon workflows.
upstream implementation ../tools/agent_tools/check_mcp_inventory.py validates MCP availability.
upstream implementation ../tools/bin/agent-canon exposes mcp-preflight-policy and mcp-inventory commands.
upstream design ../agents/canonical/CODEX_WORKFLOW.md routes MCP evidence only when needed.
downstream design ./derived-repo-bootstrap-runbook.md links MCP triage for derived repos.
@dependency-end
-->

# MCP Preflight And Fallback Policy

MCP evidence is required only when the task depends on MCP behavior or edits
MCP-related configuration. GitHub-only read inspection, ordinary consultation,
and local file edits that do not touch MCP stay outside MCP preflight.

## Decision Matrix

| Request kind | MCP preflight | Fallback |
| --- | --- | --- |
| GitHub Actions / PR / issue read-only inspection | not applicable | allowed; record no local repo task |
| Repo read-only state inspection where MCP context is the evidence | required | report unavailable and use shell only if MCP is not the subject |
| `.codex/config.toml`, `mcp/`, repo MCP tool, or goal-loop MCP gate edit | required | no implicit fallback |
| PR/issue mutation through GitHub CLI | not MCP-dependent | use `gh` authority rules |
| MCP server implementation/debug | required | stop and fix MCP or record blocker |

## Commands

```bash
tools/bin/agent-canon mcp-preflight-policy --request-kind github-actions-read
tools/bin/agent-canon mcp-inventory --root . --require repo_mcp_server --session-cache
python3 tools/agent_tools/check_mcp_inventory.py --require repo_mcp_server --report-dir reports/agents/<run-id>
```

If Rust CLI or local Cargo cannot read AgentCanon lockfiles, record
`mcp_preflight_unavailable=<reason>` and continue with Python/shell validation
unless MCP runtime behavior itself is the task scope.

## Closeout Evidence

Record one of:

- `mcp_preflight=pass` with command output.
- `mcp_preflight=not_applicable` with request-kind reason.
- `mcp_preflight=unavailable` with reason and whether fallback was safe.

Write operations that require MCP authority must not silently continue through a
different tool surface.
