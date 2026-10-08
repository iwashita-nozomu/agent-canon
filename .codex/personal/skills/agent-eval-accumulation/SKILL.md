---
name: agent-eval-accumulation
description: "Use when AgentCanon eval collection or repair is selected to establish required evidence; runs registered producers, validates family accumulation, and archives reports. Read-only observation of missing, stale, or failing evidence alone does not activate this repair loop."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":3,"record_digest":"b5d6229d3c7b63e3a9dc64276f094248ae2cbe7d54aeebbf7deb4cc47e29dd34"} -->

<!--
@dependency-start
contract skill
responsibility Exposes agent-eval-accumulation for runtime discovery.
upstream design ../../../../agents/skills/agent-eval-accumulation.md owner
@dependency-end
-->

# agent-eval-accumulation

## Canonical Skill

Canonical workflow and policy: [agent-eval-accumulation](../../../../agents/skills/agent-eval-accumulation.md).

## Tool Commands

<!-- skill-tool-commands:start -->
`python3 tools/agent/skills/skill_tool_commands.py show --skill agent-eval-accumulation --format text`
<!-- skill-tool-commands:end -->

1. Read the canonical owner before applying this skill.
