---
name: empirical-prompt-tuning
description: "Use when a reusable skill, prompt, or instruction surface needs fresh empirical evaluation against frozen baseline and hold-out scenarios, followed by evidence-based iteration to convergence."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":3,"record_digest":"1da2ba2d9c986cc28d42af4e8de3bc48a1e3626e2bf90ff4358f140712badf55"} -->

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
