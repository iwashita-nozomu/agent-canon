---
name: start-repository
description: "Use when starting a new GitHub/submodule-first repository from this template after clone, including project slug/display-name setup and AgentCanon submodule validation."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":1,"record_digest":"1c3f4d4fcb5b835103e60b0247c7f53b4933ded7d01c2c1fc3bf607ee48313ec"} -->

<!--
@dependency-start
contract skill
responsibility Exposes start-repository for runtime discovery.
upstream design ../../../agents/skills/start-repository.md owner
@dependency-end
-->

# start-repository

## Canonical Skill

Canonical workflow and policy: [start-repository](../../../agents/skills/start-repository.md).

## Tool Commands

<!-- skill-tool-commands:start -->
`python3 tools/agent_tools/skill_tool_commands.py show --skill start-repository --format text`
<!-- skill-tool-commands:end -->

1. Read the canonical owner before applying this skill.
