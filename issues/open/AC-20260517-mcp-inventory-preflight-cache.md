# MCP Inventory Preflight Should Be Session Scoped

<!--
@dependency-start
responsibility Records the operational finding that MCP inventory checks are too noisy when repeated for every repository task.
upstream design ../README.md defines AgentCanon operational issue conventions.
upstream design ../../.codex/README.md documents MCP inventory preflight.
upstream design ../../mcp/README.md documents AgentCanon repo MCP ownership.
upstream design ../../agents/skills/codex-task-workflow.md routes MCP preflight for repository tasks.
upstream implementation ../../tools/agent_tools/check_mcp_inventory.py checks configured Codex MCP inventory.
downstream implementation ../../.codex/hooks/mcp_session_context.sh should communicate the scoped preflight rule.
downstream implementation ../../tests/agent_tools/test_check_mcp_inventory.py should verify any cache or evidence behavior.
downstream implementation ../../tests/agent_tools/test_codex_hooks.py should verify hook context wording.
@dependency-end
-->

issue_id: AC-20260517-mcp-inventory-preflight-cache
status: open
source: user
severity: S2
evidence: .codex/hooks/mcp_session_context.sh
affected_surfaces: .codex/hooks/mcp_session_context.sh, .codex/README.md, mcp/README.md, agents/skills/codex-task-workflow.md, agents/canonical/CODEX_WORKFLOW.md, tools/agent_tools/check_mcp_inventory.py, tests/agent_tools/test_check_mcp_inventory.py, tests/agent_tools/test_codex_hooks.py
edit_scope: reports/dependency-review/mcp-inventory-preflight-20260517/dependency_edit_scope.txt
required_action: Replace per-message MCP inventory repetition with session-scoped or run-scoped evidence while preserving fail-closed repair behavior when MCP configuration is missing or stale.
close_condition: MCP preflight docs, hook context, checker behavior, and tests define when cached evidence is valid, when revalidation is required, and how run bundles record the evidence.

## Finding

AgentCanon currently instructs agents to run
`python3 tools/agent_tools/check_mcp_inventory.py --require repo_mcp_server`
for repository tasks. That keeps MCP setup fail-closed, but it also creates
visible repetition when a user is sending a sequence of small repo-related
messages in the same working session.

The bad user experience is not the existence of the check. The problem is that
the policy does not distinguish these cases:

- first repository action in a session or run bundle
- later repository messages after the same inventory has already passed
- configuration or branch changes that should invalidate cached evidence
- failure or missing MCP state that must still block and repair before work

## Required Fix

- Define session-scoped or run-scoped MCP inventory evidence.
- Keep the default fail-closed behavior when `repo_mcp_server` is missing,
  disabled, or not launched by the canonical `.codex/config.toml` command.
- Avoid requiring every small follow-up repository message to execute and print
  the same inventory check when no relevant runtime surface changed.
- Record cache invalidation triggers, such as changes to `.codex/config.toml`,
  `mcp/`, `tools/agent_tools/check_mcp_inventory.py`, or the active run bundle.
- Update tests for the checker and hook context wording.

## Evidence

Durable-surface search was run with:

```bash
rg -l "MCP inventory|check_mcp_inventory|repo_mcp_server|MCP_INVENTORY|mcp preflight|preflight" \
  issues memory notes/failures documents agents tools tests .codex mcp \
  > /workspace/reports/dependency-review/mcp-inventory-preflight-20260517/search_hits.txt
```

The search produced 71 hits. The dependency-expanded review initially exposed
an unrelated existing dependency-header defect in
`tools/legacy/jax_solver_util/oop_check_support/README.md`; after repairing
that stale target reference, the review produced `REPO_DEPENDENCY_REVIEW=pass`
and `DEPENDENCY_EDIT_SCOPE_PATHS=2237`.
