# MCP Inventory Preflight Should Be Session Scoped

<!--
@dependency-start
contract issue
responsibility Records the operational finding that MCP inventory checks are too noisy when repeated for every repository task.
upstream design ../README.md defines AgentCanon operational issue conventions.
upstream design ../../.codex/README.md documents MCP inventory preflight.
upstream design ../../documents/codex-configuration-reference.md documents MCP configuration boundaries.
upstream design ../../documents/template-agent-canon-audit-resolution.md records repo-local MCP inventory retirement.
upstream design ../../agents/skills/codex-task-workflow.md routes MCP preflight for repository tasks.
@dependency-end
-->

issue_id: AC-20260517-mcp-inventory-preflight-cache
status: resolved
source: user
severity: S2
evidence: .codex/hooks/mcp_session_context.sh
github_issue: https://github.com/iwashita-nozomu/agent-canon/issues/256
affected_surfaces: agent-canon-environment.toml, .codex/README.md, agents/skills/codex-task-workflow.md, agents/canonical/CODEX_WORKFLOW.md, documents/codex-configuration-reference.md, documents/template-agent-canon-audit-resolution.md
edit_scope: reports/dependency-review/mcp-inventory-preflight-20260517/dependency_edit_scope.txt
required_action: Replace per-message MCP inventory repetition with Rust session-scoped or run-scoped evidence while preserving fail-closed repair behavior when MCP configuration is missing or stale.
close_condition: Rust MCP preflight docs, hook context, checker behavior, environment TOML, and tests define when cached evidence is valid, when revalidation is required, and how run bundles record the evidence.
resolved_by: PR #87; Rust mcp-preflight-policy, mcp-inventory --session-cache, environment docs, and tests define scoped evidence and invalidation.
resolved_at: 2026-06-07

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

## 2026-05-17 Implementation Direction

The fix belongs in the Rust CLI, not in another Python helper. The expected
machine surfaces are:

- `agent-canon mcp-preflight-policy --request-kind <kind>` for classifying
  ordinary consultation, GitHub-only read inspection, and local repository
  tasks.
- `agent-canon mcp-inventory --root . --require repo_mcp_server --session-cache`
  for repository-task inventory with session-scoped pass evidence.
- `agent-canon-environment.toml` for the machine-readable environment contract,
  including cache path and invalidation surfaces.
- `python3 tools/agent_tools/check_mcp_inventory.py --report-dir <run>` remains
  only when `workflow_monitoring.md` needs direct evidence.

Observed command smoke:

```text
MCP_PREFLIGHT_SCOPE=github-actions-read
MCP_PREFLIGHT_DECISION=skip
MCP_PREFLIGHT_REASON=github_only_read_inspection

MCP_PREFLIGHT_SCOPE=implementation
MCP_PREFLIGHT_DECISION=required
MCP_PREFLIGHT_REASON=local_repo_state_or_mutation

MCP_SERVER=repo_mcp_server status=enabled command=bash args=mcp/repo_mcp_server.sh cwd=.
MCP_INVENTORY_CACHE=written
MCP_INVENTORY=pass
```

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
