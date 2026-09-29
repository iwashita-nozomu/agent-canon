---
name: task-routing
description: "Use when choosing short AgentCanon tool, skill, profile, check, runtime, closeout, or evidence routes from long candidate names, broad workflow text, routing misses, over-constrained related-skill candidates, public/system skill delegation, skill splitting, or skill/tool routing refactors."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":3,"record_digest":"23d8ec64ac2aa64dca5affa51073fb1c54eb93dd8048aa753b03dbb6559a34bb"} -->

<!--
@dependency-start
contract skill
responsibility Exposes task-routing for runtime discovery.
upstream design ../../../../agents/skills/task-routing.md owner
@dependency-end
-->

# task-routing

## Canonical Skill

Canonical workflow and policy: [task-routing](../../../../agents/skills/task-routing.md).

## Tool Commands

<!-- skill-tool-commands:start -->
`python3 tools/agent/skills/skill_tool_commands.py show --skill task-routing --format text`
<!-- skill-tool-commands:end -->

1. Read the canonical owner before applying this skill.
