---
name: empirical-prompt-tuning
description: "Use when a reusable skill, prompt, or instruction surface needs fresh empirical evaluation against frozen baseline and hold-out scenarios, followed by evidence-based iteration to convergence."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":3,"record_digest":"f457ed8fb8c9eeebc04e388fa2e0ba4d652d73b8009915666f3807f1c7d71bc7"} -->

<!--
@dependency-start
contract skill
responsibility Exposes empirical-prompt-tuning for runtime discovery.
upstream design ../../../../agents/skills/empirical-prompt-tuning.md owner
@dependency-end
-->

# empirical-prompt-tuning

## Canonical Skill

Canonical workflow and policy: [empirical-prompt-tuning](../../../../agents/skills/empirical-prompt-tuning.md).

## Tool Commands

<!-- skill-tool-commands:start -->
`python3 tools/agent/skills/skill_tool_commands.py show --skill empirical-prompt-tuning --format text`
<!-- skill-tool-commands:end -->

1. Read the canonical owner before applying this skill.
