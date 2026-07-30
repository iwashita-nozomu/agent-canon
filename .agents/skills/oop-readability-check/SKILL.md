---
name: oop-readability-check
description: "Use when the user asks to run the OOP readability checker, SOLID check, OOP check, readability check, produce a mechanical OOP report table, or interpret/prioritize OOP readability results; keep mechanical tool output separate from agent analysis."
---
<!-- generated: agent_canon.skill_runtime_shim.v1 -->
<!-- source: agents/skills/catalog.yaml#skill:oop-readability-check -->
<!-- canonical: agents/skills/oop-readability-check.md sha256=a4d54861c3388cf6c5b340133d21bb18b7765b91f79e536a95f3c5ec7d2b4b85 -->
<!-- route: agents/skills/catalog.yaml#skill:oop-readability-check.routing digest=bb3d89ba9d1db9a6007b3cef2601174b6a950c12850b566684639b217be106d1 -->
<!-- dependencies: agents/skills/skill-dependencies.yaml#invocation:oop-readability-check digest=3ceeae86534bd675b142a2760ae269df6bb49165786fdaa15876921e2db116dd -->
<!-- commands: agents/skills/catalog.yaml#skill:oop-readability-check.tool_commands digest=223ff4fa1d40e426b7c85973b0576cd6f19dbb89497264b0f9854d67aac0e35e -->
<!-- host-config: path=../.agents/skills/oop-readability-check/SKILL.md index=35 order=35 enabled=true digest=35954eec9fc5915008697cd5954dd5b92072d3bff1bc9fbdd1c1902d4d8b5da0 -->
<!-- toolcalls: tools/agent_tools/agent_team.py#materialize_skill_tool_call_token digest=e1f6464cf3f3797b1d3b3b6095a077dd2e11aaa342e097bb36ec62346293cebf -->
<!-- materializer: skill_shim_materializer.v1 -->

<!--
@dependency-start
contract skill
responsibility Exposes oop-readability-check for runtime discovery.
upstream design ../../../agents/skills/oop-readability-check.md owner
@dependency-end
-->

# oop-readability-check

## Canonical Skill

Canonical workflow and policy: [oop-readability-check](../../../agents/skills/oop-readability-check.md).

## Tool Commands

<!-- skill-tool-commands:start -->
`python3 tools/agent_tools/skill_tool_commands.py show --skill oop-readability-check --format text`
<!-- skill-tool-commands:end -->

1. Read the canonical owner before applying this skill.
