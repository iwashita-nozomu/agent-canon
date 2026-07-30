---
name: dependency-module-change
description: "Use when a dependency source change, topic branch clone, or reconstructibility-based clone cleanup is required."
---
<!-- generated: agent_canon.skill_runtime_shim.v1 -->
<!-- source: agents/skills/catalog.yaml#skill:dependency-module-change -->
<!-- canonical: agents/skills/dependency-module-change.md sha256=a78e6e956eea291fc69795b309c214a839b6db38eb9b63b10ff73c069db70978 -->
<!-- route: agents/skills/catalog.yaml#skill:dependency-module-change.routing digest=480ca2a53bcef269adb16b237607f3d3be00c07de3ab35c544a8a6351c2c7705 -->
<!-- dependencies: agents/skills/skill-dependencies.yaml#invocation:dependency-module-change digest=73f5b1d62b4728d1bfe316aefa66846e46b69218f5bece3c11ac8a4cad8d1e12 -->
<!-- commands: agents/skills/catalog.yaml#skill:dependency-module-change.tool_commands digest=9e9f48e9152005566cf65f7567442b2f770380b368e2f4ee8d8b6849c8c98623 -->
<!-- host-config: path=../.agents/skills/dependency-module-change/SKILL.md index=17 order=17 enabled=true digest=b07b2b4dc4ac372785a5a0fddd64c9ce6942b2041d920de051421a857d09c4c3 -->
<!-- toolcalls: tools/agent_tools/agent_team.py#materialize_skill_tool_call_token digest=fb432b35b77e20b9c249b5c7881bdf5b7e81e9248688939c551efa6190b4521d -->
<!-- materializer: skill_shim_materializer.v1 -->

<!--
@dependency-start
contract skill
responsibility Exposes dependency-module-change for runtime discovery.
upstream design ../../../agents/skills/dependency-module-change.md owner
@dependency-end
-->

# dependency-module-change

## Canonical Skill

Canonical workflow and policy: [dependency-module-change](../../../agents/skills/dependency-module-change.md).

## Tool Commands

<!-- skill-tool-commands:start -->
`python3 tools/agent_tools/skill_tool_commands.py show --skill dependency-module-change --format text`
<!-- skill-tool-commands:end -->

1. Read the canonical owner before applying this skill.
