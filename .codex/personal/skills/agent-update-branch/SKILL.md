---
name: agent-update-branch
description: "Use when private knowledge, eval results, AgentCanon pins, or other agent-runtime updates should be isolated on template-derived update branches and later integrated through a controlled branch workflow."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":3,"record_digest":"2dfe2912bf2a3e5791b85f60e971237cd4ce8553bb76e0e570a021156968a18e"} -->

<!--
@dependency-start
contract skill
responsibility Exposes agent-update-branch for runtime discovery.
upstream design ../../../../agents/skills/agent-update-branch.md owner
@dependency-end
-->

# agent-update-branch

## Canonical Skill

Canonical workflow and policy: [agent-update-branch](../../../../agents/skills/agent-update-branch.md).

## Tool Commands

<!-- skill-tool-commands:start -->
`python3 tools/agent/skills/skill_tool_commands.py show --skill agent-update-branch --format text`
<!-- skill-tool-commands:end -->

1. Read the canonical owner before applying this skill.
