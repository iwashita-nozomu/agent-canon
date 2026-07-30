<!--
@dependency-start
contract data
responsibility Defines the answer-free discovery-selection fresh packet.
upstream design ../../../../../documents/design/skill-runtime-shim-materialization.md approved packet contract
downstream implementation ../../../../../tools/agent_tools/skill_shim_evaluation.py packet producer
@dependency-end
-->

# Fresh Shim Discovery Selection

## Prompt Under Test

You are given a task that requires coordinated repository implementation. Inspect the
available public skill discovery surface, identify the canonical owner for the selected
workflow, and report the owner boundary and read-only command-packet route. Keep the
evaluation read-only and do not modify repository files.

## Canonical Target Files

- `.agents/skills/agent-orchestration/SKILL.md`
- `agents/skills/agent-orchestration.md`

## Prompt Dependency Files

- `agents/skills/catalog.yaml`
- `agents/skills/skill-dependencies.yaml`
- `documents/codex/prompt-skill-evaluation-checklist.md`

## Frozen Scenario

Start from a fresh evaluator instance with no prior route, packet, or reasoning context.
Inspect the host discovery adapter and follow its canonical relative link before reading
the owner policy.

## Requirements

- identify the discovered public skill
- follow the canonical owner link
- keep route authority and policy prose with their owners

## Method

Use one fresh read-only gpt-5.4-mini evaluator at medium host profile.

## Report Grammar

Report the discovered skill, canonical owner path, command-packet read path, and any
boundary concern using the observed-report grammar from the checklist.
