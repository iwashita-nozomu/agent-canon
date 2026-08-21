---
name: agent-update-branch
description: "Use when Memory, eval results, AgentCanon pins, or other agent-runtime updates should be isolated on template-derived update branches and later integrated through a controlled branch workflow."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":2,"record_digest":"97e54e19d03a45e36d6073243168bfd28e9a2183eded41186f22446abdc732ec"} -->

<!--
@dependency-start
contract skill
responsibility Exposes agent-update-branch for runtime discovery.
upstream design ../../../agents/skills/agent-update-branch.md owner
@dependency-end
-->

# agent-update-branch

## Canonical Skill

Canonical workflow and policy: [agent-update-branch](../../../agents/skills/agent-update-branch.md).

## Tool Commands

<!-- skill-tool-commands:start -->
`python3 tools/agent_tools/skill_tool_commands.py show --skill agent-update-branch --format text`
<!-- skill-tool-commands:end -->

1. Read the canonical owner before applying this skill.
