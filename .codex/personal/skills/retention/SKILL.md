---
name: retention
description: "Use when planning whether existing experiment results should be retained, archived, externalized, or deleted before mutation."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":3,"record_digest":"8589fa8d2ab0566a13c133aa8ea7302901567acb2d56df23211c0e1952083a30"} -->

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
