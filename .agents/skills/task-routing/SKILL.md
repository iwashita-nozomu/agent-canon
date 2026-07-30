---
name: task-routing
description: "Use when choosing short AgentCanon tool, skill, profile, check, runtime, closeout, or evidence routes from long candidate names, broad workflow text, routing misses, over-constrained related-skill candidates, public/system skill delegation, skill splitting, or skill/tool routing refactors."
---
<!-- generated: agent_canon.skill_runtime_shim.v1 -->
<!-- source: agents/skills/catalog.yaml#skill:task-routing -->
<!-- canonical: agents/skills/task-routing.md sha256=be32626dab962267dc9229f93d19a4a1abec015c4ccf80b3fe37eaefd4801938 -->
<!-- route: agents/skills/catalog.yaml#skill:task-routing.routing digest=8d98862013a741d63075e56acdedc1bc49afa889b0dd6807830516ccd47ff90e -->
<!-- dependencies: agents/skills/skill-dependencies.yaml#invocation:task-routing digest=728ab411a06957e0dfe7ba3fdc10b3e4a2816dad67a8dcc7ba9d2528b12be33e -->
<!-- commands: agents/skills/catalog.yaml#skill:task-routing.tool_commands digest=8d50bc5876068ebf98320357f259bc3674336a3f104956b8fb27c67451d3089d -->
<!-- host-config: path=../.agents/skills/task-routing/SKILL.md index=52 order=52 enabled=true digest=394ff3acb2242f455b3d1429afa06782f887bf88aca34d9039a1405025068c42 -->
<!-- toolcalls: tools/agent_tools/agent_team.py#materialize_skill_tool_call_token digest=902b21cb88af4fa27b7aa4ad74c7683bb7c6553b056bdf1e57722f599e8aed0e -->
<!-- materializer: skill_shim_materializer.v1 -->

<!--
@dependency-start
contract skill
responsibility Exposes task-routing as a Codex runtime discovery adapter.
upstream design ../../../agents/skills/task-routing.md canonical skill owner
@dependency-end
-->

# task-routing

## Canonical Skill

Canonical workflow and policy: [task-routing](../../../agents/skills/task-routing.md).

## Tool Commands

<!-- skill-tool-commands:start -->
`python3 tools/agent_tools/skill_tool_commands.py show --skill task-routing --format text`
<!-- skill-tool-commands:end -->

1. Read the canonical owner before applying this skill.
