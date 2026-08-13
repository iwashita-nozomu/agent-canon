# task-routing
<!--
@dependency-start
contract skill
responsibility Selects one canonical skill route plus evidence-backed deferred candidates without duplicate routing state sets.
upstream design ../canonical/skills.md skill canon registry
upstream design ../../documents/design/tool-skill-routing-refactor.md short tool and skill naming policy
upstream design ../../documents/design/responsibility-rationale.md routing-state rationale
upstream design ./agent-orchestration.md owns later Decision Sufficiency and write-safety policy
downstream implementation ../../tools/agent_tools/route.py selects short routing areas
downstream implementation ../../tests/agent_tools/test_task_routing_fast_path.py validates packet-free ordinary routing
upstream design ./skill-dependencies.yaml owns typed skill prerequisites, successors, order, and parallel relations
downstream implementation ../../tools/agent_tools/skill_route_catalog.py derives invocation order
downstream implementation ../../tools/agent_tools/skill_dependency_map.py validates and generates dependency graph
@dependency-end
-->

## Purpose

Choose the minimum skill/tool route from a prompt, changed paths, or explicit area. Ordinary routing does not require a Decision Sufficiency packet; later high-risk or genuinely ambiguous implementation owners may invoke that policy through `agent-orchestration`.

## Canonical output

Routing has two authoritative concepts:

```text
SELECTED_SKILLS=<ordered skills that should execute now>
DEFERRED_CANDIDATES=<candidate skills + activation evidence still required>
```

`SELECTED_SKILLS` is the one source of truth for execution. Deferred candidates do not execute until their evidence becomes true.

Historical names such as `SKILLS`, `ACTIVE_SKILLS`, `MATCHED_SKILLS`, `RELATED_SKILLS`, or `RELATED_SKILL_CANDIDATES` may be accepted as compatibility reads while callers migrate, but they are not independent state owners. New consumers read only the canonical selected/candidate state. If compatibility projections are emitted, they must be derived from the canonical state and may not carry extra routing meaning.

## Operation

Use `python3 tools/agent_tools/route.py --prompt ...` or the canonical changed-path route. Select the smallest owner set whose responsibilities are reachable from the request. Add a candidate only with a concrete activation condition; do not execute candidates preemptively or replace routing with another classifier/handoff schema.

## Boundary

Routing chooses owners; selected skills own their execution and validation. `agent-orchestration` owns coordination, later implementation decisions, and write safety.
