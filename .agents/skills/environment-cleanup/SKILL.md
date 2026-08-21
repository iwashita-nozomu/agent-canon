---
name: environment-cleanup
description: "Use when environment dependencies or runtime capabilities need cleanup through dependency-design and environment-maintenance with version, scope, security, and rollback evidence."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":2,"record_digest":"fa9e1979126ae9e6989980117d1364a87fb79c7df660d37ecbcc998889faa162"} -->

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
