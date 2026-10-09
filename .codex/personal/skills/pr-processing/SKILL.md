---
name: pr-processing
description: "Use for an authorized GitHub Issue or PR operation; build a queue only when candidates depend on or conflict with each other."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":3,"record_digest":"c46f2eb29e78f8904350b2d4c3bacdf5078ad69710805cfa7bf9ce2f3d26e0d4"} -->

<!--
@dependency-start
contract skill
responsibility Exposes pr-processing for runtime discovery.
upstream design ../../../../agents/skills/pr-processing.md owner
@dependency-end
-->

# pr-processing

## Canonical Skill

Canonical workflow and policy: [pr-processing](../../../../agents/skills/pr-processing.md).

## Tool Commands

<!-- skill-tool-commands:start -->
`python3 tools/agent/skills/skill_tool_commands.py show --skill pr-processing --format text`
<!-- skill-tool-commands:end -->

1. Read the canonical owner before applying this skill.
