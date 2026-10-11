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
| workflow family, activation, and full-staging route | `agents/task_catalog.yaml` `workflow_activation_policy`; `workflow_families[].id` |
| stage topology and required roles | `agents/task_catalog.yaml` `role_topology_defaults.stage_waves`; `workflow_families[].roles` |
| default specialists and review packs | `agents/task_catalog.yaml`; `agents/agents_config.json` |
| role behavior, stage conditions, and review separation | `.codex/agents/*.toml` |
| selected Skills, execution readiness, and same-run result transitions | `bootstrap_agent_run.py`; `skill_document_reader.py`; `workflow_monitor.py` |
| skill selection | `agents/skills/catalog.yaml`; `.codex/personal/skills/*/SKILL.md`; `python3 tools/agent/orchestration/route.py --prompt` |
| implementation stage and closeout | [agents/skills/codex-task-workflow.md](skills/codex-task-workflow.md); selected family row in `agents/task_catalog.yaml` |
| active design packet schema | [agents/COMMUNICATION_PROTOCOL.md](COMMUNICATION_PROTOCOL.md); `agents/agents_config.json#artifacts.active_design_packet` |
| semantic responsibility allocation | [documents/design/semantic-responsibility-contract.md](../documents/design/semantic-responsibility-contract.md); run-local instance via active-packet `source_refs` |
| closeout authority | `task_close.py`; `report_artifact_checks.py` |
| validation failure response taxonomy | `documents/runtime/runtime-profiles-and-check-matrix.json`; generated reader projection: [documents/runtime/runtime-profiles-and-check-matrix.md](../documents/runtime/runtime-profiles-and-check-matrix.md) |
| validation failure response workflow projections | [agents/canonical/CODEX_WORKFLOW.md](canonical/CODEX_WORKFLOW.md); [agents/canonical/CODEX_SUBAGENTS.md](canonical/CODEX_SUBAGENTS.md); [documents/conventions/REVIEW_PROCESS.md](../documents/conventions/REVIEW_PROCESS.md) |

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
- selected canonical Skill bodies read through file EOF
- current execution-graph status and ready ToolCalls
- same-run result input route for actual host/child results
- validation route

Subagent handoffs carry that machine-readable packet and the run bundle paths.
The runtime dispatches only the ready graph frontier. A launch result is not a
completion result; subsequent stages wait for actual child results passed with
the same run ID. `workflow_monitor.py` projects those results into the existing
wave event readback; it does not decide readiness. The run manifest's
`execution_graph.result_readback` retains the actual results used to unlock
each node and is the closeout input; a monitoring or schedule status alone
cannot establish graph completion.
Tool routing is carried through `team_manifest.yaml` under
`run.repo_tool_routing_policy`. Selected tools are invoked through their existing
CLI, API, script, or Make entrypoint with native argv and retain the configured
execution, permission, environment, and validation guarantees. A related skill
becoming active in a later wave selects that owner directly; no private command
packet or regenerated binding projection is required before handoff.

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

The selected task family and Skill packets define the production stage graph;
the active packet's typed entries provide its selected graph anchors and
materialization reader path. `bootstrap_agent_run.py` is the sole dispatcher:
it loads selected canonical Skill documents and required prerequisites through
EOF, dispatches non-conflicting ready nodes via existing ToolCalls, and advances
only from actual host results. Hooks remain partial observations and do not
control scheduling. `task_close.py` remains the sole terminal predicate.

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

`workflow_activation_policy` selects the positive family/stage/child route. Safety,
authority, and validation prohibitions stay with their canonical owners;
[documents/runtime/runtime-profiles-and-check-matrix.md](../documents/runtime/runtime-profiles-and-check-matrix.md) selects the active
validation matrix for the changed path and risk class.

## Execution Result Readback

The runtime uses actual results for graph readiness. Run-local execution
results and readback stay in existing artifacts:

- `team_manifest.yaml` `run.execution_graph.result_readback` is read by task
  closeout as the execution-result owner
- `workflow_monitoring.md` `Actual Wave Events` is the matching event readback
- `schedule.md` `Agent Wave Ledger` is a display projection only
- `team_manifest.yaml` `run.delegated_spawn_policy`
- `team_manifest.yaml` `run.subagent_lifecycle_policy`

The runtime cap is in `.codex/config.toml`; family budgets are in
`agents/task_catalog.yaml`. Do not add a parallel wave planner or use these
readback rows as completion authority.

## Validation

- `python3 tools/validation/semantic/runtime/check_agent_runtime_alignment.py`
- `python3 tools/validation/semantic/convention/check_convention_compliance.py`
- `python3 tools/runtime/lifecycle/task_close.py ...`
