# Template AgentCanon Audit 500 Resolution

<!--
@dependency-start
contract issue
responsibility Records resolution of the 2026-05-16 Template / AgentCanon 500 item audit.
upstream design ../README.md defines durable AgentCanon operational issue storage.
upstream design ../../documents/template-agent-canon-audit-resolution.md records the audit coverage ledger.
upstream design ../../documents/runtime-profiles-and-check-matrix.md defines profile and risk-based validation routing.
downstream design ../../README.md exposes the profile policy in the AgentCanon overview.
@dependency-end
-->

issue_id: AC-20260516-template-agent-canon-audit-500
status: resolved
source: user
severity: S1
evidence: user-supplied audit artifact archived locally as parent reports/template_agent_canon_audit_500_issues.md; tracked coverage ledger in ../../documents/template-agent-canon-audit-resolution.md
github_issue: https://github.com/iwashita-nozomu/agent-canon/issues/252
affected_surfaces: README.md, QUICK_START.md, Makefile, ROOT_AGENTS.md, agents/canonical/CODEX_WORKFLOW.md, agents/skills/start-repository.md, agents/skills/catalog.yaml, documents/runtime-profiles-and-check-matrix.md, documents/template-agent-canon-audit-resolution.md, documents/SHARED_RUNTIME_SURFACES.md, documents/shared-runtime-surfaces.toml, documents/tools/README.md, tools/sync_agent_canon.sh
edit_scope: documents/runtime-profiles-and-check-matrix.md, documents/template-agent-canon-audit-resolution.md, README.md, ROOT_AGENTS.md, agents/canonical/CODEX_WORKFLOW.md, agents/skills/start-repository.md, agents/skills/catalog.yaml, documents/SHARED_RUNTIME_SURFACES.md, documents/shared-runtime-surfaces.toml, documents/tools/README.md, tools/catalog.yaml, tools/sync_agent_canon.sh, parent README.md, parent QUICK_START.md, parent Makefile, parent documents/README.md
required_action: Convert broad always-on rules and legacy wording into profile-based, risk-based, or compatibility-only policy while preserving required MCP and AgentCanon source ownership constraints.
close_condition: The audit has a coverage ledger for I-001 through I-500, high-level Template and AgentCanon entrypoints point at the profile/check matrix, start-repository no longer advertises local bare seeding, and user-facing sync help hides legacy subtree/snapshot routes.
resolved_by: pending commit in current AgentCanon PR branch
resolved_at: 2026-05-16

## Finding

The 500-item audit showed the same failure pattern across many files:

- installed runtime surfaces were described as always-required project surfaces;
- full workflow, closeout, validation, and review gates were applied too broadly;
- legacy local bare, subtree, snapshot, and compatibility routes were still
  visible in normal user-facing guidance;
- skill and tool catalog surfaces lacked a clear way to say optional or
  maintainer-only;
- the Template quick path mixed base project work with Docker, C++, GitHub,
  experiment, memory, and agent maintenance profiles.

## Resolution

The fix is category-level because the audit items are repetitive by design.
`documents/template-agent-canon-audit-resolution.md` maps every audit ID range
from I-001 through I-500 to one of the implemented policy outcomes:
`profiled`, `risk_based`, `compatibility_only`, `canon_source`, or
`higher_priority_override`.

The MCP optionality recommendations are intentionally not applied because the
current repo runtime requires `repo_mcp_server` inventory checks for repository
tasks.
