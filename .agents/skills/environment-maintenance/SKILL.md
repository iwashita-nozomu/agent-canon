---
name: environment-maintenance
description: "Use when touching Docker, CI, dependencies, runtime compatibility, or repository-level development environment instructions."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":1,"record_digest":"fb9ed9f109d8013c7b758548266bc64821e682be5a64eeb26996653d5bb0f08e"} -->

<!--
@dependency-start
contract skill
responsibility Exposes environment-maintenance for runtime discovery.
upstream design ../../../agents/skills/environment-maintenance.md owner
@dependency-end
-->

# environment-maintenance

## Canonical Skill

Canonical workflow and policy: [environment-maintenance](../../../agents/skills/environment-maintenance.md).

## Tool Commands

<!-- skill-tool-commands:start -->
`python3 tools/agent_tools/skill_tool_commands.py show --skill environment-maintenance --format text`
<!-- skill-tool-commands:end -->

1. Read the canonical owner before applying this skill.
