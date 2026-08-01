---
name: change-review
description: "Use for code review, doc review, or AI-generated diff review when you need findings-first output focused on bugs, regressions, missing tests, and broken assumptions."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":1,"record_digest":"be50c17e2188dedb0fc82992596d50ee75a7fa3fd60e1d4a00c92cb45453a5c9"} -->

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
