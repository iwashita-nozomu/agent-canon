---
name: skill-cleanup
description: "Use when canonical skill docs, catalog, dependency DAG, routes, tool commands, generated shims, host config, graph, or readback must be cleaned as one unit."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":1,"record_digest":"d0494ac89b8a02ef3410ef4a1fda2419888a31a6f776b47feb0396e4f8cb0470"} -->

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
