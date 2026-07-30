---
name: tool-finding-report
description: "Use when running tools, checkers, hooks, static analysis, or structural analyzers to find problems, preserve raw and structured full finding artifacts, mechanically rank every finding, and produce a complete finding report for implementation or refactor planning; before/after impact is optional when explicitly requested."
---
<!-- generated: agent_canon.skill_runtime_shim.v1 -->
<!-- source: agents/skills/catalog.yaml#skill:tool-finding-report -->
<!-- canonical: agents/skills/tool-finding-report.md sha256=c17c9c83b20184fcb61937d24d95912540b296df7429da70b750a733c878b6a3 -->
<!-- route: agents/skills/catalog.yaml#skill:tool-finding-report.routing digest=c4efc1f6d5c496198e24285312873ccf59fee23f28859f6165573e2610b4de5c -->
<!-- dependencies: agents/skills/skill-dependencies.yaml#invocation:tool-finding-report digest=73a0440bb18fb73e90cbe91c224e13749583a0c5427287daf292f3053ebe7c65 -->
<!-- commands: agents/skills/catalog.yaml#skill:tool-finding-report.tool_commands digest=6eda060338d24a6523c50b3fa28833fcb602844d273aa72e3f228f9d41e6cea2 -->
<!-- host-config: path=../.agents/skills/tool-finding-report/SKILL.md index=54 order=54 enabled=true digest=752712b9092f56360a7cd962f0afa9c1a7d53fbe19f1619c9bb341aa60debbbf -->
<!-- toolcalls: tools/agent_tools/agent_team.py#materialize_skill_tool_call_token digest=b1ac85861b792e4cf98336c6c6b0baba94e168251fb6976cb6dc56724d9da934 -->
<!-- materializer: skill_shim_materializer.v1 -->

<!--
@dependency-start
contract skill
responsibility Exposes tool-finding-report for runtime discovery.
upstream design ../../../agents/skills/tool-finding-report.md owner
@dependency-end
-->

# tool-finding-report

## Canonical Skill

Canonical workflow and policy: [tool-finding-report](../../../agents/skills/tool-finding-report.md).

## Tool Commands

<!-- skill-tool-commands:start -->
`python3 tools/agent_tools/skill_tool_commands.py show --skill tool-finding-report --format text`
<!-- skill-tool-commands:end -->

1. Read the canonical owner before applying this skill.
