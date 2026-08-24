<!--
@dependency-start
contract reference
responsibility Defines AgentCanon issue templates and label taxonomy.
upstream design ../runtime/private-feedback-knowledge.md defines GitHub Issue authority and private packet transport.
downstream implementation ../../templates/documents/github/issue/agentcanon-maintenance.yml captures maintenance issues.
downstream implementation ../../templates/documents/github/issue/eval-capture.yml captures eval issues.
downstream implementation ../../templates/documents/github/pull-request/agent_canon.md links issue/eval closeout evidence.
@dependency-end
-->

# AgentCanon Issue Label Taxonomy

The machine-readable status lifecycle mapping is owned by
[`issue-label-taxonomy.toml`](issue-label-taxonomy.toml). Tools load that TOML
record and verify the canonical labels against the remote repository catalog;
this Markdown page remains explanatory documentation.

Use labels to make runtime profile, affected surface, and evaluation need visible
before implementation starts.

Core labels:

| Label | Meaning |
| --- | --- |
| `agent-canon` | Shared AgentCanon source or runtime policy is affected. |
| `maintenance` | Operational maintenance, cleanup, route repair, or runbook work. |
| `agent-quality` | Agent behavior, routing, role, prompt, or guardrail quality. |
| `eval` | Requires an eval case or explicit not-evaluable rationale. |
| `workflow` | Workflow family, task routing, or closeout path. |
| `tooling` | Tool, hook, checker, CLI, CI, or catalog surface. |
| `docs` | Reader-facing documentation or runbook surface. |
| `github` | GitHub Actions, PR template, issue template, or GitHub automation surface. |
| `mcp` | MCP preflight, server, inventory, or alternate route behavior. |
| `submodule` | AgentCanon pin/update/root-view propagation behavior. |

Issue templates require runtime profile, affected path, validation, eval
decision, rollback consideration, and closeout evidence. The maintenance form
also requires an operational current snapshot: what happened, why the change is
needed, completed/in-progress work, remaining work, and the blocked update
operation with evidence and an unblock condition. A missing blocker is recorded
as `none` with a reason so that "not observed" and "not blocked" remain distinct.
Status labels describe lifecycle state; the form snapshot supplies the evidence
behind that state and does not define a second status state machine.

Existing issues should be backfilled opportunistically when they are edited or
resolved; do not rewrite issue history just to add labels or the new snapshot
fields.
