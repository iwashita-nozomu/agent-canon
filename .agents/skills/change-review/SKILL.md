---
name: change-review
description: "Use for code review, doc review, or AI-generated diff review when you need findings-first output focused on bugs, regressions, missing tests, and broken assumptions."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":2,"record_digest":"d47e52e51ebc4f2ecab9d92ceb52d1a655c88ea46bd4f63c06e32fc4227e644e"} -->

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
