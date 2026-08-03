---
name: refactor-loop
description: "Use when a large refactor should run as a behavior-preserving refactor loop with explicit path mapping, semantic-delta controls, repair slices, and strong review gates."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":1,"record_digest":"79f3f136475081caea89e1b83a883349030949e6c1db0e8d788af6130d217cec"} -->

<!--
@dependency-start
contract skill
responsibility Exposes refactor-loop for runtime discovery.
upstream design ../../../agents/skills/refactor-loop.md owner
@dependency-end
-->

# refactor-loop

## Canonical Skill

Canonical workflow and policy: [refactor-loop](../../../agents/skills/refactor-loop.md).

## Tool Commands

<!-- skill-tool-commands:start -->
`python3 tools/agent_tools/skill_tool_commands.py show --skill refactor-loop --format text`
<!-- skill-tool-commands:end -->

1. Read the canonical owner before applying this skill.
