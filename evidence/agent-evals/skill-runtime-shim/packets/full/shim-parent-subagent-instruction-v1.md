<!--
@dependency-start
contract data
responsibility Defines the answer-free parent versus subagent instruction packet.
upstream design ../../../../../documents/design/skill-runtime-shim-materialization.md packet contract
downstream implementation ../../../../../tools/agent_tools/skill_shim_evaluation.py packet producer
@dependency-end
-->

# Fresh Shim Parent Subagent Instruction

## Prompt Under Test

A parent agent must delegate one implementation responsibility. Inspect the discovery
adapter and its canonical owner, then report the parent and subagent instruction boundary.
Keep the evaluation read-only and do not assign work from adapter prose.

## Canonical Target Files

- `.codex/personal/skills/subagent-bootstrap/SKILL.md`
- `agents/skills/subagent-bootstrap.md`

## Prompt Dependency Files

- `agents/skills/catalog.yaml`
- `agents/canonical/CODEX_SUBAGENTS.md`

## Requirements

- identify the parent owner responsibility
- preserve the subagent instruction boundary
- identify the canonical owner read path

## Method

Use one fresh read-only gpt-5.4-mini evaluator at medium host profile.
