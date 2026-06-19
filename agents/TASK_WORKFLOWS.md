<!--
@dependency-start
responsibility Documents Agent Task Workflows for this repository.
upstream design README.md agent canon overview.
upstream design ../documents/runtime-profiles-and-check-matrix.md runtime profile and validation routing policy.
upstream implementation task_catalog.yaml workflow family defaults.
upstream implementation agents_config.json permanent team and role mapping.
upstream design canonical/CODEX_SUBAGENTS.md subagent role contract.
downstream design workflows/implementation-waterfall-workflow.md stage gate implementation flow.
downstream implementation ../tools/agent_tools/task_start.py emits workflow packets.
downstream implementation ../tools/agent_tools/bootstrap_agent_run.py creates workflow run bundles.
downstream implementation ../tools/agent_tools/workflow_monitor.py records dynamic wave events.
@dependency-end
-->

# Agent Task Workflows

This file is a workflow reader map. It points to the owner surfaces that select
workflow family, roles, skills, stage gates, wave budgets, and closeout checks.

## Workflow Contract Owners

| Contract | Owner Surface |
| -------- | ------------- |
| workflow family and spawn budget | `agents/task_catalog.yaml` |
| role topology and same-role instance schema | `agents/task_catalog.yaml` |
| default specialists and review packs | `agents/task_catalog.yaml`; `agents/agents_config.json` |
| role behavior, stage conditions, and review separation | `.codex/agents/*.toml` |
| run bundle, declared workflow / skills / review, and dynamic wave ledger | `task_start.py`; `bootstrap_agent_run.py`; `workflow_monitor.py` |
| skill selection | `agents/skills/catalog.yaml`; `.agents/skills/*/SKILL.md`; `agent-canon local-llm route-skill` |
| implementation stage gate | `agents/workflows/implementation-waterfall-workflow.md` |
| implementation packet schema | `agents/COMMUNICATION_PROTOCOL.md`; run bundle design packet |
| closeout authority | `task_close.py`; `report_artifact_checks.py` |

Contract edits start in the owner surface. This reader map changes when the
reader path changes.

## Common Evidence Packet

`task_start.py` and `bootstrap_agent_run.py` emit:

- workflow family
- active and deferred skills
- review roles
- document packets
- initial wave recommendation
- dynamic expansion waves
- wave-record command
- validation route

Subagent handoffs carry that machine-readable packet and the run bundle paths.

## Design Artifact Shape

Implementation design is owned by the run bundle design packet and the
implementation-waterfall workflow. The required reader-facing anchors are:

- `Abstract Design Frame`
- `Implementation Flow Graph`
- `Implementation Source Packet`
- `Design Side-Effect Map`
- `Design-To-Implementation Trace`

The graph ties request clauses and compact findings to mechanical scope,
implementation slices, validation, review, sync, and closeout.

## Workflow Family Reader Paths

| Family | Owner Row |
| ------ | --------- |
| Scoped Change Lite | `agents/task_catalog.yaml` `workflow_families[].id=scoped_change_lite` |
| Scoped Change | `agents/task_catalog.yaml` `workflow_families[].id=scoped_change` |
| Research-Driven Change | `agents/task_catalog.yaml` `workflow_families[].id=research_driven_change` |
| Large Delivery | `agents/task_catalog.yaml` `workflow_families[].id=large_delivery` |
| Platform And Environment | `agents/task_catalog.yaml` `workflow_families[].id=platform_and_environment` |
| Comprehensive Development | `agents/task_catalog.yaml` `workflow_families[].id=comprehensive_development` |
| Adaptive Improvement Loop | `agents/task_catalog.yaml` `workflow_families[].id=adaptive_improvement_loop` |

`documents/runtime-profiles-and-check-matrix.md` selects the active validation
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

- `python3 tools/agent_tools/check_agent_runtime_alignment.py`
- `python3 tools/agent_tools/check_convention_compliance.py`
- `python3 tools/agent_tools/task_close.py ...`
