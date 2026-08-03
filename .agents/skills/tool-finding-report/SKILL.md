---
name: tool-finding-report
description: "Use when running tools, checkers, hooks, static analysis, or structural analyzers to find problems, preserve raw and structured full finding artifacts, mechanically rank every finding, and produce a complete finding report for implementation or refactor planning; before/after impact is optional when explicitly requested."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":1,"record_digest":"b0b303669e61ce06ac88f8147cd771e48dff665c1972f08bfc48c8ec4741817d"} -->

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
