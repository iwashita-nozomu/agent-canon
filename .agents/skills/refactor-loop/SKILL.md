---
name: refactor-loop
description: "Use when a large refactor should run as a behavior-preserving refactor loop with explicit path mapping, semantic-delta controls, repair slices, and strong review gates."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":2,"record_digest":"e76f70082d4afabbaeaacfa77aefe7ef5c3bdde4c053789dddade4ccdebb9a34"} -->

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
