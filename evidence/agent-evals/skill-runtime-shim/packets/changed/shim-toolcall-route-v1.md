<!--
@dependency-start
contract data
responsibility Defines the answer-free typed ToolCall route fresh packet.
upstream design ../../../../../documents/design/skill-runtime-shim-materialization.md approved packet contract
downstream implementation ../../../../../tools/agent_tools/skill_shim_evaluation.py packet producer
@dependency-end
-->

# Fresh Shim ToolCall Route

## Prompt Under Test

A changed repository task needs the command packet for a structured planning skill. Read
the discovery adapter, resolve its canonical owner, and obtain the complete packet through
the owner command producer. Distinguish ToolID, ToolCall, argument schema, and failure
semantics. Keep the evaluation read-only and do not invent an execution payload.

## Canonical Target Files

- `.codex/personal/skills/structure-planning/SKILL.md`
- `agents/skills/structure-planning.md`

## Prompt Dependency Files

- `agents/skills/catalog.yaml`
- `agents/skills/skill-dependencies.yaml`
- `documents/design/skill-tool-invocation-graph.md`

## Frozen Scenario

Use a fresh evaluator instance with no prior command packet or route context. Follow the
adapter's relative owner link, then use the read-only packet path and inspect typed graph
references without copying payloads into the adapter.

## Requirements

- obtain the owner command packet
- preserve typed ToolID, ToolCall, and argument-schema boundaries
- distinguish success and failure semantics

## Method

Use one fresh read-only gpt-5.4-mini evaluator at medium host profile.

## Report Grammar

Report the owner path, packet producer path, typed identity observations, and failure
semantics using the observed-report grammar from the checklist.
