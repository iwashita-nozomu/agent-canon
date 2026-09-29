---
name: skill-cleanup
description: "Use when canonical skill docs, catalog, dependency DAG, routes, tool commands, generated shims, host config, graph, or readback must be cleaned as one unit."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":3,"record_digest":"e716425a8b91b66d0ea52be3c36f3cc118e63b8bde3ee195d1f5a428d4ac53f5"} -->

<!--
@dependency-start
contract skill
responsibility Exposes skill-cleanup for runtime discovery.
upstream design ../../../../agents/skills/skill-cleanup.md owner
@dependency-end
-->

# skill-cleanup

## Canonical Skill

Canonical workflow and policy: [skill-cleanup](../../../../agents/skills/skill-cleanup.md).

## Tool Commands

<!-- skill-tool-commands:start -->
`python3 tools/agent/skills/skill_tool_commands.py show --skill skill-cleanup --format text`
<!-- skill-tool-commands:end -->

1. Read the canonical owner before applying this skill.
