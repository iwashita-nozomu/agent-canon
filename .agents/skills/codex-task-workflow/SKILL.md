---
name: codex-task-workflow
description: "Use when Codex needs a context-independent execution path for a repository task, from intake and workflow selection through artifact placement, implementation, validation, and closeout."
---
<!-- generated: agent_canon.skill_runtime_shim.v1 -->
<!-- source: agents/skills/catalog.yaml#skill:codex-task-workflow -->
<!-- canonical: agents/skills/codex-task-workflow.md sha256=047323aa293163a6feee3b1561f57da751726151829a5b9eed22afca36e8d869 -->
<!-- route: agents/skills/catalog.yaml#skill:codex-task-workflow.routing digest=b62ef8a5d9dc51d40389f5adf349b920943c2308ed63611356e325874293760b -->
<!-- dependencies: agents/skills/skill-dependencies.yaml#invocation:codex-task-workflow digest=2af7374d7e96f1a1fad66ce67b13639c9d2be77e05a5860b6868d2139d327afb -->
<!-- commands: agents/skills/catalog.yaml#skill:codex-task-workflow.tool_commands digest=2da88620dbd973c3caba0a131a13ea99fa0323a286eaa9105ed64c9c537d8a38 -->
<!-- host-config: path=../.agents/skills/codex-task-workflow/SKILL.md index=12 order=12 enabled=true digest=331959a55a170456b4147d13058534a60b19e793127abfaa38c57c3c2316a058 -->
<!-- toolcalls: tools/agent_tools/agent_team.py#materialize_skill_tool_call_token digest=03d83161ef44496e2801831958213dbd80b686dbd476026ab7c51a9776bfb025 -->
<!-- materializer: skill_shim_materializer.v1 -->

<!--
@dependency-start
contract skill
responsibility Exposes codex-task-workflow for runtime discovery.
upstream design ../../../agents/skills/codex-task-workflow.md owner
@dependency-end
-->

# codex-task-workflow

## Canonical Skill

Canonical workflow and policy: [codex-task-workflow](../../../agents/skills/codex-task-workflow.md).

## Tool Commands

<!-- skill-tool-commands:start -->
`python3 tools/agent_tools/skill_tool_commands.py show --skill codex-task-workflow --format text`
<!-- skill-tool-commands:end -->

1. Read the canonical owner before applying this skill.
