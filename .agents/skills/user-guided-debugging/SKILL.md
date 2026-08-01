---
name: user-guided-debugging
description: "Use when the user explicitly asks to debug, repair, or refactor one issue at a time with visible problem statements before each edit and a next-issue prompt after each scoped fix."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":1,"record_digest":"1aa9a0d571eb7b10abcd16917e3b125857ff3d387f452715b7f6fb9e903ef8b1"} -->

<!--
@dependency-start
contract skill
responsibility Exposes user-guided-debugging for runtime discovery.
upstream design ../../../agents/skills/user-guided-debugging.md owner
@dependency-end
-->

# user-guided-debugging

## Canonical Skill

Canonical workflow and policy: [user-guided-debugging](../../../agents/skills/user-guided-debugging.md).

## Tool Commands

<!-- skill-tool-commands:start -->
`python3 tools/agent_tools/skill_tool_commands.py show --skill user-guided-debugging --format text`
<!-- skill-tool-commands:end -->

1. Read the canonical owner before applying this skill.
