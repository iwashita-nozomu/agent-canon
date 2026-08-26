<!--
@dependency-start
contract data
responsibility Defines the answer-free dependent skill ordering packet.
upstream design ../../../../../documents/design/skill-runtime-shim-materialization.md packet contract
downstream implementation ../../../../../tools/agent_tools/skill_shim_evaluation.py packet producer
@dependency-end
-->

# Fresh Shim Dependent Skill Ordering

## Prompt Under Test

A repository task needs orchestration and a dependent skill. Inspect the discovery
adapter, follow its canonical owner, and report the dependency-backed ordering without
inventing a route from shim prose. Keep the evaluation read-only.

## Canonical Target Files

- `.codex/personal/skills/agent-orchestration/SKILL.md`
- `agents/skills/agent-orchestration.md`

## Prompt Dependency Files

- `agents/skills/catalog.yaml`
- `agents/skills/skill-dependencies.yaml`

## Requirements

- identify dependency ordering from the owner data
- preserve the canonical owner boundary
- report the packet read path

## Method

Use one fresh read-only gpt-5.4-mini evaluator at medium host profile.
