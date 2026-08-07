---
name: skill-cleanup
description: "Use when canonical skill docs, catalog, dependency DAG, routes, tool commands, generated shims, host config, graph, or readback must be cleaned as one unit."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":1,"record_digest":"59c3d8b16367d9cc3675364dd9ab7bd4db572a39e1b337e2a417147fb85ef145"} -->

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
