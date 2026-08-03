---
name: skill-cleanup
description: "Use when canonical skill docs, catalog, dependency DAG, routes, tool commands, generated shims, host config, graph, or readback must be cleaned as one unit."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":1,"record_digest":"beac79c15c4b1f085e6576e32cfe9dc7b7969fefb52c369bb0cb4188e4a26ebb"} -->

<!--
@dependency-start
contract skill
responsibility Exposes skill-cleanup for runtime discovery.
upstream design ../../../agents/skills/skill-cleanup.md owner
@dependency-end
-->

# skill-cleanup

## Canonical Skill

Canonical workflow and policy: [skill-cleanup](../../../agents/skills/skill-cleanup.md).

## Tool Commands

<!-- skill-tool-commands:start -->
`python3 tools/agent_tools/skill_tool_commands.py show --skill skill-cleanup --format text`
<!-- skill-tool-commands:end -->

1. Read the canonical owner before applying this skill.
