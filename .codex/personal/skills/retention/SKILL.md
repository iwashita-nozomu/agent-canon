---
name: retention
description: "Use when planning whether existing experiment results should be retained, archived, externalized, or deleted before mutation."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":3,"record_digest":"d5336670fc0b31d30fb526310a42a6692bf4edae4006f55cdb440b150790f80c"} -->

<!--
@dependency-start
contract skill
responsibility Exposes retention for runtime discovery.
upstream design ../../../../agents/skills/retention.md owner
@dependency-end
-->

# retention

## Canonical Skill

Canonical workflow and policy: [retention](../../../../agents/skills/retention.md).

## Tool Commands

<!-- skill-tool-commands:start -->
`python3 tools/agent/skills/skill_tool_commands.py show --skill retention --format text`
<!-- skill-tool-commands:end -->

1. Read the canonical owner before applying this skill.
