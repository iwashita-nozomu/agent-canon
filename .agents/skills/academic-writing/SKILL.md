---
name: academic-writing
description: "Use when drafting a paper, thesis chapter, scholarly note, or other academic document that needs mandatory multi-agent review for notation, logic, and reader flow."
---
<!-- generated: agent_canon.skill_runtime_shim.v1 -->
<!-- source: agents/skills/catalog.yaml#skill:academic-writing -->
<!-- canonical: agents/skills/academic-writing.md sha256=10805ab5b5209a240851efba887de0e3d6d38d80babdeeafc175489a24674792 -->
<!-- route: agents/skills/catalog.yaml#skill:academic-writing.routing digest=ca10bf6d75f42cd4327f5f00eb4a2d4bd60d989e5e15e07e1277226fff1a36cc -->
<!-- dependencies: agents/skills/skill-dependencies.yaml#invocation:academic-writing digest=4cda45473cbe5fe4639378efbbac6b3b38a044c67ea77a6b9995a427c471c1a7 -->
<!-- commands: agents/skills/catalog.yaml#skill:academic-writing.tool_commands digest=703255f0944030af93160b0d7ede6dd1ed560897a8e1ba31970cebf73f2bba2d -->
<!-- host-config: path=../.agents/skills/academic-writing/SKILL.md index=0 order=0 enabled=true digest=16efdda96cf04b3b8f3130864c4e412a3b0b737189f28a73f932174b5b4e5e81 -->
<!-- toolcalls: tools/agent_tools/agent_team.py#materialize_skill_tool_call_token digest=5df014d7123849b32b06e2a42f9176b358524d231b0a2b1a5089e2d1b6ba6a3b -->
<!-- materializer: skill_shim_materializer.v1 -->

<!--
@dependency-start
contract skill
responsibility Exposes academic-writing for runtime discovery.
upstream design ../../../agents/skills/academic-writing.md owner
@dependency-end
-->

# academic-writing

## Canonical Skill

Canonical workflow and policy: [academic-writing](../../../agents/skills/academic-writing.md).

## Tool Commands

<!-- skill-tool-commands:start -->
`python3 tools/agent_tools/skill_tool_commands.py show --skill academic-writing --format text`
<!-- skill-tool-commands:end -->

1. Read the canonical owner before applying this skill.
