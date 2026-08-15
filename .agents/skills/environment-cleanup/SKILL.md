---
name: environment-cleanup
description: "Use when environment dependencies or runtime capabilities need cleanup through dependency-design and environment-maintenance with version, scope, security, and rollback evidence."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":2,"record_digest":"9b611e2cdc07b54de199a3b2f55698c7b254f4e4c6ba55929c0885028402c2df"} -->

<!--
@dependency-start
contract skill
responsibility Exposes environment-cleanup for runtime discovery.
upstream design ../../../agents/skills/environment-cleanup.md owner
@dependency-end
-->

# environment-cleanup

## Canonical Skill

Canonical workflow and policy: [environment-cleanup](../../../agents/skills/environment-cleanup.md).

## Tool Commands

<!-- skill-tool-commands:start -->
`python3 tools/agent_tools/skill_tool_commands.py show --skill environment-cleanup --format text`
<!-- skill-tool-commands:end -->

1. Read the canonical owner before applying this skill.
