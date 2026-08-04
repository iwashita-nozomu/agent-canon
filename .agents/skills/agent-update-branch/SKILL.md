---
name: agent-update-branch
description: "Use when Memory, eval results, AgentCanon pins, or other agent-runtime updates should be isolated on template-derived update branches and later integrated through a controlled branch workflow."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":1,"record_digest":"f148bd374a3517f762af08c057673bcc1601a7b8e083c5c91a9a2e33c1120c79"} -->

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
