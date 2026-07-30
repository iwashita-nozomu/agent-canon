<!--
@dependency-start
contract data
responsibility Defines the answer-free boundary-negative fresh packet.
upstream design ../../../../../documents/design/skill-runtime-shim-materialization.md approved packet contract
downstream implementation ../../../../../tools/agent_tools/skill_shim_evaluation.py packet producer
@dependency-end
-->

# Fresh Shim Boundary And Negative

## Prompt Under Test

Consider three repository requests: an unrelated task, a task delegated to a host-provided
system skill, and a request to change canonical skill prose. Inspect the public discovery
adapter and owner surfaces, then report which local skill surface is relevant and which
requests remain outside its authority. Keep the evaluation read-only.

## Canonical Target Files

- `.agents/skills/task-routing/SKILL.md`
- `agents/skills/task-routing.md`

## Prompt Dependency Files

- `agents/skills/catalog.yaml`
- `documents/codex/prompt-skill-evaluation-checklist.md`

## Frozen Scenario

Use a fresh evaluator instance and do not reuse a prior answer, route, command, or
interpretation. Inspect only the target adapter, its canonical owner, the catalog owner,
and the checklist.

## Requirements

- avoid activation for an unrelated request
- preserve host delegation boundaries
- keep canonical prose out of the runtime adapter

## Method

Use one fresh read-only gpt-5.4-mini evaluator at medium host profile.

## Report Grammar

Record the observed activation, owner-following, and boundary result with the observed-report
grammar from the checklist.
