---
name: task-routing
description: "Use when choosing short AgentCanon tool, skill, profile, check, runtime, closeout, or evidence routes from long candidate names, broad workflow text, routing misses, over-constrained related-skill candidates, public/system skill delegation, skill splitting, or skill/tool routing refactors."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":2,"record_digest":"1fb5a0978a5d404a0bc6dddc6955e759657282bff5b0f6ce3dd6ad5e7608c171"} -->

<!--
@dependency-start
contract skill
responsibility Exposes task-routing for runtime discovery.
upstream design ../../../agents/skills/task-routing.md owner
@dependency-end
-->

# task-routing

## Canonical Skill

Canonical workflow and policy: [task-routing](../../../agents/skills/task-routing.md).

## Tool Commands

<!-- skill-tool-commands:start -->
`python3 tools/agent_tools/skill_tool_commands.py show --skill task-routing --format text`
<!-- skill-tool-commands:end -->

1. Read the canonical owner before applying this skill.
