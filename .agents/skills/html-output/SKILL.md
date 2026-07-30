---
name: html-output
description: "Use when the user explicitly asks for HTML output, a browser-readable page, dashboard/report HTML, external browser publication, or local preview server; defaults reports to Markdown unless HTML is explicit."
---
<!-- generated: agent_canon.skill_runtime_shim.v1 -->
<!-- source: agents/skills/catalog.yaml#skill:html-output -->
<!-- canonical: agents/skills/html-output.md sha256=3743668c77956ea0368326287a6759d76a4b824a09a0b4fd1b0873f32d88e1b0 -->
<!-- route: agents/skills/catalog.yaml#skill:html-output.routing digest=a3724897179885d50f35b9cdca676b197d9285abb4b36f33cd75806e24316a63 -->
<!-- dependencies: agents/skills/skill-dependencies.yaml#invocation:html-output digest=63c8377b1a4ef67c4612aaf6be6beb92d8c14827bdfc0447f1cc3b518e2e0047 -->
<!-- commands: agents/skills/catalog.yaml#skill:html-output.tool_commands digest=7148e6f7fa8485ccae896e2d462e0da053ab682f8f816b6ccae382b0713b6184 -->
<!-- host-config: path=../.agents/skills/html-output/SKILL.md index=29 order=29 enabled=true digest=c4ec1dce0bd1abeb7bec6307300eef340ba5a0f7227a043f883e1eae5213a20e -->
<!-- toolcalls: tools/agent_tools/agent_team.py#materialize_skill_tool_call_token digest=3416d5ea49bc788f430110108f1928f4ae78665a5db6d61bd86684609bf3bbef -->
<!-- materializer: skill_shim_materializer.v1 -->

<!--
@dependency-start
contract skill
responsibility Exposes html-output as a Codex runtime discovery adapter.
upstream design ../../../agents/skills/html-output.md canonical skill owner
@dependency-end
-->

# html-output

## Canonical Skill

Canonical workflow and policy: [html-output](../../../agents/skills/html-output.md).

## Tool Commands

<!-- skill-tool-commands:start -->
`python3 tools/agent_tools/skill_tool_commands.py show --skill html-output --format text`
<!-- skill-tool-commands:end -->

1. Read the canonical owner before applying this skill.
