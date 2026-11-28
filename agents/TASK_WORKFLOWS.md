<!--
@dependency-start
contract workflow
responsibility Documents Agent Task Workflows for this repository.
upstream design README.md agent canon overview.
upstream design ../documents/runtime/runtime-profiles-and-check-matrix.md runtime profile and validation routing policy.
upstream implementation task_catalog.yaml workflow family defaults.
upstream implementation agents_config.json permanent team and role mapping.
upstream design canonical/CODEX_SUBAGENTS.md subagent role contract.
downstream design skills/codex-task-workflow.md implementation stage and closeout flow.
downstream implementation ../tools/runtime/dispatch/agent-canon/src/compare_agent_run_paths.rs compares expected and actual routes.
@dependency-end
-->

# Agent Task Workflows

## Reader Map

Use the tables below to find the owner for a workflow family, role, Skill, or
validation decision.

## Workflow Contract Owners

| Contract | Owner Surface |
| -------- | ------------- |
| workflow family and role guidance | `agents/task_catalog.yaml` `workflow_families[].id`, `workflow_families[].roles` |
| default specialists and review packs | `agents/task_catalog.yaml`; `agents/agents_config.json` |
| role behavior and write authority | `.codex/agents/*.toml` |
| skill selection | `agents/skills/catalog.yaml`; `.codex/personal/skills/*/SKILL.md`; `tools/bin/agent-canon route --prompt` |
| implementation guidance and closeout | [agents/skills/codex-task-workflow.md](skills/codex-task-workflow.md); selected family row in `agents/task_catalog.yaml` |
| closeout authority | `agents/canonical/CODEX_COMPLETION.md`; `tools/runtime/dispatch/agent-canon/src/report_artifact_checks.rs` |
| validation failure response taxonomy | `documents/runtime/runtime-profiles-and-check-matrix.json`; generated reader projection: [documents/runtime/runtime-profiles-and-check-matrix.md](../documents/runtime/runtime-profiles-and-check-matrix.md) |
| validation failure response workflow projections | [agents/canonical/CODEX_WORKFLOW.md](canonical/CODEX_WORKFLOW.md); [agents/canonical/CODEX_SUBAGENTS.md](canonical/CODEX_SUBAGENTS.md); [documents/conventions/REVIEW_PROCESS.md](../documents/conventions/REVIEW_PROCESS.md) |

## Native Coordination

Use [native collaboration](COMMUNICATION_PROTOCOL.md#native-collaboration) and
the [handoff packet](COMMUNICATION_PROTOCOL.md#handoff-packet).

## Design Artifact Shape

Keep selected design and review artifacts at the project owner paths. Share their
actual paths and relevant clauses in the handoff; no team manifest is required.

- `Abstract Design Frame`
- `Implementation Source Packet`
- `Design Side-Effect Map`
- `Design-To-Implementation Trace`

Each selected artifact states the relevant assumptions, owner, inputs, outputs,
and review evidence. Preserve those references through native handoff.

When a design contains semantic deltas, the implementation source packet also
references `artifact:semantic_responsibility_contract.toml`. The populated
instance is created from the existing project template,
allocates obligations before implementation, and is not copied into the
repository-wide template or policy.

## Workflow Family Reader Paths

| Family | Owner Row |
| ------ | --------- |
| Owner-Bounded Change | `agents/task_catalog.yaml` `workflow_families[].id=owner_bounded_change` |
| Scoped Change | `agents/task_catalog.yaml` `workflow_families[].id=scoped_change` |
| Research-Driven Change | `agents/task_catalog.yaml` `workflow_families[].id=research_driven_change` |
| Large Delivery | `agents/task_catalog.yaml` `workflow_families[].id=large_delivery` |
| Platform And Environment | `agents/task_catalog.yaml` `workflow_families[].id=platform_and_environment` |
| Comprehensive Development | `agents/task_catalog.yaml` `workflow_families[].id=comprehensive_development` |
| Adaptive Improvement Loop | `agents/task_catalog.yaml` `workflow_families[].id=adaptive_improvement_loop` |
| IssueWorker Publication | `agents/task_catalog.yaml` `workflow_families[].id=issue_worker_publication`; logical route executes the `publisher` role for explicit candidates |

## Actual Route Evidence

Expected paths are read from linked workflow and Skill instructions. Actual
route events and outcomes use the existing evidence surfaces:

- hook logs record behavior events
- native ToolCall results distinguish spawn, completion, and failure
- existing Eval owners compare expected and actual routes and evaluate validity

Do not infer a required route or successful completion from a manifest or
monitor row alone. A route difference alone is not an Eval failure.

## Validation

- `tools/bin/agent-canon check-agent-runtime-alignment`
- `agent-canon check-convention-compliance`
