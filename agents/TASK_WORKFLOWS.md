<!--
@dependency-start
contract workflow
responsibility Documents Agent Task Workflows for this repository.
upstream design README.md agent canon overview.
upstream design ../documents/runtime/runtime-profiles-and-check-matrix.md runtime profile and validation routing policy.
upstream implementation task_catalog.yaml workflow family defaults.
upstream implementation agents_config.json permanent team and role mapping.
upstream design canonical/CODEX_SUBAGENTS.md subagent role contract.
downstream design workflows/implementation-waterfall-workflow.md stage gate implementation flow.
downstream implementation ../tools/runtime/lifecycle/bootstrap_agent_run.py emits workflow packets and creates workflow run bundles.
downstream implementation ../tools/runtime/lifecycle/workflow_monitor.py records dynamic wave events.
downstream implementation ../tools/validation/semantic/runtime/check_agent_runtime_alignment.py validates the canonical packet owner marker.
@dependency-end
-->

# Agent Task Workflows

## Reader Map

This file is a workflow reader map. It points to the owner surfaces that select
workflow family, roles, skills, stage gates, wave budgets, and closeout checks.
Use `Workflow Contract Owners` to find the canonical owner, `Common Evidence
Packet` to understand task/run handoff data, `Design Artifact Shape` for
implementation design anchors, and `Workflow Family Reader Paths` to route by
family. This file maps readers to owner surfaces; it does not replace the
task catalog, runtime profile matrix, or closeout tools as policy authority.

## Workflow Contract Owners

| Contract | Owner Surface |
| -------- | ------------- |
| workflow family and spawn budget | `agents/task_catalog.yaml` |
| role topology and same-role instance schema | `agents/task_catalog.yaml` |
| default specialists and review packs | `agents/task_catalog.yaml`; `agents/agents_config.json` |
| role behavior, stage conditions, and review separation | `.codex/agents/*.toml` |
| run bundle, declared workflow / skills / review, and dynamic wave ledger | `bootstrap_agent_run.py`; `workflow_monitor.py` |
| skill selection | `agents/skills/catalog.yaml`; `.codex/personal/skills/*/SKILL.md`; `python3 tools/agent/orchestration/route.py --prompt` |
| implementation stage gate | `agents/workflows/implementation-waterfall-workflow.md` |
| active design packet schema | `agents/COMMUNICATION_PROTOCOL.md`; `agents/agents_config.json#artifacts.active_design_packet` |
| semantic responsibility allocation | `documents/design/semantic-responsibility-contract.md`; run-local instance via active-packet `source_refs` |
| closeout authority | `task_close.py`; `report_artifact_checks.py` |
| validation failure response taxonomy | `documents/runtime/runtime-profiles-and-check-matrix.json`; generated reader projection: `documents/runtime/runtime-profiles-and-check-matrix.md` |
| validation failure response workflow projections | `agents/canonical/CODEX_WORKFLOW.md`; `agents/canonical/CODEX_SUBAGENTS.md`; `documents/conventions/REVIEW_PROCESS.md` |

Contract edits start in the owner surface. This reader map changes when the
reader path changes.

## Common Evidence Packet

`bootstrap_agent_run.py` emits:

- workflow family
- active and deferred skills
- selected skill tool route sequence
- dynamic skill routing candidates
- tool catalog match surface
- review roles
- document packets
- initial wave recommendation
- dynamic expansion waves
- wave-record command
- validation route

Subagent handoffs carry that machine-readable packet and the run bundle paths.
Tool routing is carried through `team_manifest.yaml` under
`run.repo_tool_routing_policy`. Each selected skill has a sequential command
packet: show the skill packet, run required commands, run task-matching
conditional commands, then run validation commands. When a related skill becomes
active in a later wave, the same `skill_tool_commands.py show --skill <skill>`
packet is regenerated for that skill before the handoff proceeds.

## Design Artifact Shape

Implementation design is owned by the neutral closed active design packet
`waterfall.design_packet.v1`, persisted at
`team_manifest.yaml#run.active_design_packet`. The selected artifact paths,
review paths, and `document_flow_required` flag remain the main runtime fields;
the closed graph contract adds one clause registry and four typed entries. The
persisted `active_design_packet_reference_projection` binds those entries to
source bytes, dependency endpoints, selected outputs, and review identities.
Chat, schedule prose, history, and inferred headings are not packet authority.

- `Abstract Design Frame`
- `Implementation Source Packet`
- `Design Side-Effect Map`
- `Design-To-Implementation Trace`

Each entry declares its exact clause, owner, source, dependency, output, and
reviewer references. Chat, schedule prose, history, and inferred headings are
not packet authority. `agent_team.py::create_run_bundle` is the sole public
delegator: it resolves the packet, validates all references, renders every
projection, and atomically publishes the complete bundle for task-start,
bootstrap, and document-start producers. One responsibility unit remains one
implementation handoff even when its internal work is dependency ordered.

When a design contains semantic deltas, the implementation source packet also
references `artifact:semantic_responsibility_contract.toml`. The populated
instance is created from the reusable template in the current run bundle,
allocates obligations before implementation, and is not copied into the
repository-wide template or policy.

## Implementation Flow Graph

The implementation waterfall remains the production stage graph; the active
packet's typed entries provide its selected graph anchors and materialization
reader path.

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

`documents/runtime/runtime-profiles-and-check-matrix.md` selects the active validation
matrix for the changed path and risk class.

## Dynamic Wave Evidence

Wave state is recorded in run bundle artifacts:

- `schedule.md` `Agent Wave Ledger`
- `workflow_monitoring.md` `Actual Wave Events`
- `team_manifest.yaml` `run.delegated_spawn_policy`
- `team_manifest.yaml` `run.subagent_lifecycle_policy`

The runtime cap is in `.codex/config.toml`; family budgets are in
`agents/task_catalog.yaml`.

## Validation

- `python3 tools/validation/semantic/runtime/check_agent_runtime_alignment.py`
- `python3 tools/validation/semantic/convention/check_convention_compliance.py`
- `python3 tools/runtime/lifecycle/task_close.py ...`
