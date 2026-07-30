---
name: comprehensive-development
description: "Use when a repo-wide task spans code, docs, tools, workflows, and runtime surfaces and needs explicit subagent routing."
---
<!-- generated: agent_canon.skill_runtime_shim.v1 -->
<!-- source: agents/skills/catalog.yaml#skill:comprehensive-development -->
<!-- canonical: agents/skills/comprehensive-development.md sha256=09f4caa99d3290b9311842592b168d78e4a9d3ba4e608a517bfc58d1d64ba91e -->
<!-- route: agents/skills/catalog.yaml#skill:comprehensive-development.routing digest=c5a6312f47f5551dc5647765befe569ea80e28516cce821a2440eaab3bd83f55 -->
<!-- dependencies: agents/skills/skill-dependencies.yaml#invocation:comprehensive-development digest=bd430951132f16013dc607063a8beb8b538bf17835b4a427b2f2d03eba973d50 -->
<!-- commands: agents/skills/catalog.yaml#skill:comprehensive-development.tool_commands digest=9e940ed3794d82f12021242a0cc64838d414bcc49e74300e3a5ae4af4f01eea3 -->
<!-- host-config: path=../.agents/skills/comprehensive-development/SKILL.md index=14 order=14 enabled=true digest=4b92f15236f97f5e2243b2aec298870b7f5509354887ff09e27f96797a013155 -->
<!-- toolcalls: tools/agent_tools/agent_team.py#materialize_skill_tool_call_token digest=5f0217804a6e1478994c04fcf485e0ae899695b57c3c5baddd9fcc07c602fd39 -->
<!-- materializer: skill_shim_materializer.v1 -->

<!--
@dependency-start
contract skill
responsibility Exposes comprehensive-development for runtime discovery.
upstream design ../../../agents/skills/comprehensive-development.md owner
@dependency-end
-->

# comprehensive-development

## Canonical Skill

Canonical workflow and policy: [comprehensive-development](../../../agents/skills/comprehensive-development.md).

## Tool Commands

<!-- skill-tool-commands:start -->
`python3 tools/agent_tools/skill_tool_commands.py show --skill comprehensive-development --format text`
<!-- skill-tool-commands:end -->

1. Read the canonical owner before applying this skill.
