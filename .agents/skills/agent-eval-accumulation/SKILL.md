---
name: agent-eval-accumulation
description: "Use when accumulated AgentCanon eval evidence is missing, stale, or failing; runs registered eval producers, validates eval family accumulation, and stores evidence through the log archive instead of hand-writing reports."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":2,"record_digest":"d958ecdc2db74fc0aa278e8ac031c3c8cf767704c2aa8e2ad9e2ec2e9f836e9f"} -->

<!--
@dependency-start
contract skill
responsibility Exposes agent-eval-accumulation for runtime discovery.
upstream design ../../../agents/skills/agent-eval-accumulation.md owner
@dependency-end
-->

# agent-eval-accumulation

## Canonical Skill

Canonical workflow and policy: [agent-eval-accumulation](../../../agents/skills/agent-eval-accumulation.md).

## Tool Commands

<!-- skill-tool-commands:start -->
`python3 tools/agent_tools/skill_tool_commands.py show --skill agent-eval-accumulation --format text`
<!-- skill-tool-commands:end -->

1. Read the canonical owner before applying this skill.
