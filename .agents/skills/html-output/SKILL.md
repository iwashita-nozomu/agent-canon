---
name: html-output
description: "Use when the user explicitly asks for HTML output, a browser-readable page, dashboard/report HTML, external browser publication, or local preview server; defaults reports to Markdown unless HTML is explicit."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":1,"record_digest":"d950e04f9f61c905bcb9c84bf1ef2a456faa5f8337a816315af491394015a143"} -->

<!--
@dependency-start
contract skill
responsibility Exposes html-output for runtime discovery.
upstream design ../../../agents/skills/html-output.md owner
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
