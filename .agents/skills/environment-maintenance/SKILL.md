---
name: environment-maintenance
description: "Use when touching Docker, CI, dependencies, runtime compatibility, or repository-level development environment instructions."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":2,"record_digest":"d75d8e0e7593e070d7b07f0a9528018234fb91ca137587d6b6ef2d399e08770b"} -->

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
