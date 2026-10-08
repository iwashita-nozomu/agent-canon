---
name: change-review
description: "Use for code review, doc review, or AI-generated diff review when you need findings-first output focused on bugs, regressions, missing tests, and broken assumptions."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":3,"record_digest":"fa283a4f8f852b798dd72b566b5ba1ba40d88d7eb90be3c43a1b4ac4055ce639"} -->

<!--
@dependency-start
contract skill
responsibility Exposes change-review for runtime discovery.
upstream design ../../../../agents/skills/change-review.md owner
@dependency-end
-->

# change-review

## Canonical Skill

Canonical workflow and policy: [change-review](../../../../agents/skills/change-review.md).

## Tool Commands

<!-- skill-tool-commands:start -->
`python3 tools/agent/skills/skill_tool_commands.py show --skill change-review --format text`
<!-- skill-tool-commands:end -->

1. Read the canonical owner before applying this skill.
