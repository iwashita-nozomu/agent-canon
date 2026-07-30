---
name: algorithm-proof-exploration
description: "Use when exploring, refactoring, or choosing an algorithm under proof obligations; builds JIT-canonical IR, lemma dependency graphs, algorithmic blocker frontiers, and algorithm-change guidance before handing terminal proof work to formal-proof-workflow."
---
<!-- generated: agent_canon.skill_runtime_shim.v1 -->
<!-- source: agents/skills/catalog.yaml#skill:algorithm-proof-exploration -->
<!-- canonical: agents/skills/algorithm-proof-exploration.md sha256=c042790e52d826a43771b85ecf8f8dcb3d4dff01dfb5782f1afd2c4f84d610f8 -->
<!-- route: agents/skills/catalog.yaml#skill:algorithm-proof-exploration.routing digest=285ba77252ed0ac7692425ad9ce43f29404b1c921f112b06d4841ef46d55ad0d -->
<!-- dependencies: agents/skills/skill-dependencies.yaml#invocation:algorithm-proof-exploration digest=d9e5685bf1003aafdadeb113773d1418a6c93a5b8b209035f2e328e13280d4df -->
<!-- commands: agents/skills/catalog.yaml#skill:algorithm-proof-exploration.tool_commands digest=2bfc25363986744d4d8d058d659dede41e37cd0dcc05443a7ea40e2e750e7503 -->
<!-- host-config: path=../.agents/skills/algorithm-proof-exploration/SKILL.md index=10 order=10 enabled=true digest=0777acca6355b72061752d9395595a15801361edc64f9867929e5e1629da0727 -->
<!-- toolcalls: tools/agent_tools/agent_team.py#materialize_skill_tool_call_token digest=a4b849905374d9d5215dcc947ec35d48f82ea402d641a9a16727879a3caeed2f -->
<!-- materializer: skill_shim_materializer.v1 -->

<!--
@dependency-start
contract skill
responsibility Exposes algorithm-proof-exploration for runtime discovery.
upstream design ../../../agents/skills/algorithm-proof-exploration.md owner
@dependency-end
-->

# algorithm-proof-exploration

## Canonical Skill

Canonical workflow and policy: [algorithm-proof-exploration](../../../agents/skills/algorithm-proof-exploration.md).

## Tool Commands

<!-- skill-tool-commands:start -->
`python3 tools/agent_tools/skill_tool_commands.py show --skill algorithm-proof-exploration --format text`
<!-- skill-tool-commands:end -->

1. Read the canonical owner before applying this skill.
