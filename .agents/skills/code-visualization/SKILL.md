---
name: code-visualization
description: "Sole public visualization owner for code, repository structure, runtime behavior, state, data movement, dependencies, types, proof state, interactive graphs, and document diagrams; builds the complete typed universe and coverage manifest before delegating renderer-only projection."
---
<!-- generated: agent_canon.skill_runtime_shim.v1 -->
<!-- source: agents/skills/catalog.yaml#skill:code-visualization -->
<!-- canonical: agents/skills/code-visualization.md sha256=bf8bb1cc6d04da53c2535e9d95632c0e324c67b2cec19134a525bca5af05f4b7 -->
<!-- route: agents/skills/catalog.yaml#skill:code-visualization.routing digest=ba012b9d0ad5ca234b17c2e7c146b4e302174af6558412ba93b1521a3c80526a -->
<!-- dependencies: agents/skills/skill-dependencies.yaml#invocation:code-visualization digest=c55efa485014c1ffdcbc12e5fd00040320b0af1ac612a35d8f42f19513717fbe -->
<!-- commands: agents/skills/catalog.yaml#skill:code-visualization.tool_commands digest=b04fb561222aacd9b23a10e81a5e29e7e7c1abcfc92203cf0c066eec2f180015 -->
<!-- host-config: path=../.agents/skills/code-visualization/SKILL.md index=13 order=13 enabled=true digest=214a7aa17be76cb7211fffac6d58d4b011fe3a31ad469aa263e2060713512e7a -->
<!-- toolcalls: tools/agent_tools/agent_team.py#materialize_skill_tool_call_token digest=da5c6ff7a7e9fb4580f50c1b436c01a493d2baf8b384c40b9f402731097a6370 -->
<!-- materializer: skill_shim_materializer.v1 -->

<!--
@dependency-start
contract skill
responsibility Exposes code-visualization for runtime discovery.
upstream design ../../../agents/skills/code-visualization.md owner
@dependency-end
-->

# code-visualization

## Canonical Skill

Canonical workflow and policy: [code-visualization](../../../agents/skills/code-visualization.md).

## Tool Commands

<!-- skill-tool-commands:start -->
`python3 tools/agent_tools/skill_tool_commands.py show --skill code-visualization --format text`
<!-- skill-tool-commands:end -->

1. Read the canonical owner before applying this skill.
