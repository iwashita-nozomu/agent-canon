<!--
@dependency-start
contract reference
responsibility Defines AgentCanon issue templates and label taxonomy.
upstream design ../issues/README.md defines durable local issue storage.
downstream implementation ../.github/ISSUE_TEMPLATE/agentcanon-maintenance.yml captures maintenance issues.
downstream implementation ../.github/ISSUE_TEMPLATE/eval-capture.yml captures eval issues.
downstream implementation ../.github/PULL_REQUEST_TEMPLATE.md links issue/eval closeout evidence.
@dependency-end
-->

# AgentCanon Issue Label Taxonomy

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
decision, rollback consideration, and closeout evidence. Existing issues should
be backfilled opportunistically when they are edited or resolved; do not rewrite
issue history just to add labels.
