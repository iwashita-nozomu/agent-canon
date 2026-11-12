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

This file is a workflow reader map. It points to the owner surfaces that describe
workflow families, roles, Skills, and closeout checks.
Use `Workflow Contract Owners` to find the canonical owner, `Common Evidence
Packet` to understand task/run handoff data, `Design Artifact Shape` for
implementation design anchors, and `Workflow Family Reader Paths` to route by
family. This file maps readers to owner surfaces; it does not replace the
task catalog, runtime profile matrix, or closeout tools as policy authority.

## Workflow Contract Owners

| Contract | Owner Surface |
| -------- | ------------- |
| workflow family and role guidance | `agents/task_catalog.yaml` `workflow_families[].id`, `workflow_families[].roles` |
| default specialists and review packs | `agents/task_catalog.yaml`; `agents/agents_config.json` |
| role behavior and write authority | `.codex/agents/*.toml` |
| Skill selection and canonical Skill text | `agents/skills/catalog.yaml`; selected Skill links |
| skill selection | `agents/skills/catalog.yaml`; `.codex/personal/skills/*/SKILL.md`; `python3 tools/agent/orchestration/route.py --prompt` |
| implementation guidance and closeout | [agents/skills/codex-task-workflow.md](skills/codex-task-workflow.md); selected family row in `agents/task_catalog.yaml` |
| closeout authority | `agents/canonical/CODEX_COMPLETION.md`; `tools/runtime/dispatch/agent-canon/src/report_artifact_checks.rs` |
| validation failure response taxonomy | `documents/runtime/runtime-profiles-and-check-matrix.json`; generated reader projection: [documents/runtime/runtime-profiles-and-check-matrix.md](../documents/runtime/runtime-profiles-and-check-matrix.md) |
| validation failure response workflow projections | [agents/canonical/CODEX_WORKFLOW.md](canonical/CODEX_WORKFLOW.md); [agents/canonical/CODEX_SUBAGENTS.md](canonical/CODEX_SUBAGENTS.md); [documents/conventions/REVIEW_PROCESS.md](../documents/conventions/REVIEW_PROCESS.md) |

Contract edits start in the owner surface. This reader map changes when the
reader path changes.

## Native Coordination

Use the current Codex collaboration tools for launch, continuation, waiting, and
completion. Carry the target, agreed scope, needed source context, expected result,
and validation route in the handoff. Keep scope and progress in Git and the current
conversation. A launch is not completion; retain actual results and failures.

Read the applicable ROOT and selected Skill directly. The selected tool owner
provides its existing CLI, API, script, or Make entrypoint. Preserve its arguments,
execution boundary and results. Hook logs and Eval accumulation keep their own
existing evidence routes.

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

Family rows provide routing context rather than a dispatch schedule. Safety,
authority, and validation prohibitions stay with their canonical owners;
[documents/runtime/runtime-profiles-and-check-matrix.md](../documents/runtime/runtime-profiles-and-check-matrix.md) selects the active
validation matrix for the changed path and risk class.

## Actual Route Evidence

Expected paths are read from linked workflow and Skill instructions. Actual
route events and outcomes use the existing evidence surfaces:

- hook logs record behavior events
- native ToolCall results distinguish spawn, completion, and failure
- existing Eval owners compare expected and actual routes and evaluate validity

Do not infer a required route or successful completion from a manifest or
monitor row alone. A route difference alone is not an Eval failure.

## Validation

- `python3 tools/validation/semantic/runtime/check_agent_runtime_alignment.py`
- `python3 tools/validation/semantic/convention/check_convention_compliance.py`
