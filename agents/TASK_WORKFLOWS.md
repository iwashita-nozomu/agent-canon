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
downstream implementation ../tools/runtime/lifecycle/bootstrap_agent_run.py creates optional run-bundle metadata.
downstream implementation ../tools/runtime/lifecycle/workflow_monitor.py records actual behavior events.
downstream implementation ../tools/runtime/dispatch/agent-canon/src/task_close.rs owns native coordinated closeout checks.
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
| active design packet schema | [agents/COMMUNICATION_PROTOCOL.md](COMMUNICATION_PROTOCOL.md); `agents/agents_config.json#artifacts.active_design_packet` |
| semantic responsibility allocation | [documents/design/semantic-responsibility-contract.md](../documents/design/semantic-responsibility-contract.md); run-local instance via active-packet `source_refs` |
| closeout authority | `tools/runtime/dispatch/agent-canon/src/task_close.rs`; `tools/runtime/dispatch/agent-canon/src/report_artifact_checks.rs` |
| validation failure response taxonomy | `documents/runtime/runtime-profiles-and-check-matrix.json`; generated reader projection: [documents/runtime/runtime-profiles-and-check-matrix.md](../documents/runtime/runtime-profiles-and-check-matrix.md) |
| validation failure response workflow projections | [agents/canonical/CODEX_WORKFLOW.md](canonical/CODEX_WORKFLOW.md); [agents/canonical/CODEX_SUBAGENTS.md](canonical/CODEX_SUBAGENTS.md); [documents/conventions/REVIEW_PROCESS.md](../documents/conventions/REVIEW_PROCESS.md) |

Contract edits start in the owner surface. This reader map changes when the
reader path changes.

## Optional Run Bundle

When explicitly selected, `bootstrap_agent_run.py` can create an optional run
bundle and print workflow family, suggested Skill links, selected roles,
document packets, and a validation route. Ordinary task start does not require
a run bundle, task-catalog CLI, manifest, or readiness state.

Read the applicable `ROOT_AGENTS.md` and selected Skill directly. Markdown links
describe the expected route; native ToolCalls and their actual results and
failures describe what occurred. A launch is not a completion.
`workflow_monitor.py` records actual behavior events but does not authorize or
sequence work. Existing Eval owners compare expected and actual routes and
evaluate their validity; a route difference alone is not a failure.

Tool routing remains with each selected tool's existing CLI, API, script, or
Make entrypoint. Preserve native argv and its configured execution, permission,
environment, and validation guarantees.

## Design Artifact Shape

Implementation design is owned by the neutral closed active design packet
`waterfall.design_packet.v1`, persisted at
`team_manifest.yaml#run.active_design_packet`. The selected artifact paths,
review paths, and `document_flow_required` flag remain available to workflows
that choose to use the packet. Its persisted
`active_design_packet_reference_projection` binds packet entries to source
bytes, dependency endpoints, selected outputs, and review identities.
Chat, schedule prose, history, and inferred headings are not packet authority.

- `Abstract Design Frame`
- `Implementation Source Packet`
- `Design Side-Effect Map`
- `Design-To-Implementation Trace`

Each entry declares its exact clause, owner, source, dependency, output, and
reviewer references. Chat, schedule prose, history, and inferred headings are
not packet authority. `agent_team.py::create_run_bundle` remains an optional
bundle publisher that resolves and validates the packet when a chosen workflow
needs those artifacts.

When a design contains semantic deltas, the implementation source packet also
references `artifact:semantic_responsibility_contract.toml`. The populated
instance is created from the reusable template in the current run bundle,
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

- `workflow_monitoring.md` behavior and semantic events record observations
- native ToolCall results distinguish spawn, completion, and failure
- existing Eval owners compare expected and actual routes and evaluate validity

Do not infer a required route or successful completion from a manifest or
monitor row alone. A route difference alone is not an Eval failure.

## Validation

- `python3 tools/validation/semantic/runtime/check_agent_runtime_alignment.py`
- `python3 tools/validation/semantic/convention/check_convention_compliance.py`
- `tools/bin/agent-canon task-close ...`
