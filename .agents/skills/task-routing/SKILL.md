---
name: task-routing
description: "Use when choosing short AgentCanon tool, skill, profile, check, runtime, closeout, or evidence routes from long candidate names, broad workflow text, routing misses, over-constrained related-skill candidates, public/system skill delegation, skill splitting, or skill/tool routing refactors."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":2,"record_digest":"871c8a96d19e573419b9a3d5994a441b3de35729c9d6b3d8a82c123cbd30a95c"} -->

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
