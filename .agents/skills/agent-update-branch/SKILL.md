---
name: agent-update-branch
description: "Use when Memory, eval results, AgentCanon pins, or other agent-runtime updates should be isolated on template-derived update branches and later integrated through a controlled branch workflow."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":2,"record_digest":"8b90414c6f0b8106701ccade46d03619df8b56a73e90ede02e04c2edca3ece2c"} -->

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
