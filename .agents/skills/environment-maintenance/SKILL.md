---
name: environment-maintenance
description: "Use when touching Docker, CI, dependencies, runtime compatibility, or repository-level development environment instructions."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":2,"record_digest":"198f106a87f5e82042b6b7e139ae9ef55c59b8cac7984da7bffa2ac35b709612"} -->

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
