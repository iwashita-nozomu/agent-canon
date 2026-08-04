---
name: change-review
description: "Use for code review, doc review, or AI-generated diff review when you need findings-first output focused on bugs, regressions, missing tests, and broken assumptions."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":1,"record_digest":"1f0f1bcd30522b74c768f00c84f0e8b7a5dfc8e3745218e6b3edcceeda2e6c82"} -->

<!--
@dependency-start
contract skill
responsibility Exposes change-review for runtime discovery.
upstream design ../../../agents/skills/change-review.md owner
@dependency-end
-->

# change-review

## Canonical Skill

Canonical workflow and policy: [change-review](../../../agents/skills/change-review.md).

## Tool Commands

<!-- skill-tool-commands:start -->
`python3 tools/agent_tools/skill_tool_commands.py show --skill change-review --format text`
<!-- skill-tool-commands:end -->

1. Read the canonical owner before applying this skill.
