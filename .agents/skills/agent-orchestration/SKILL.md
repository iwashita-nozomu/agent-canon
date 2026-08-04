---
name: agent-orchestration
description: "Mandatory routing skill for repository tasks. Use before selecting workflow family, skills, review roles, subagents, model/team policy, runtime entrypoints, or run bundles for Codex routing."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":1,"record_digest":"d3f83535c3c78e5b2c4fd11ecaa040b9592644057ca1a3898895c6837e68cacc"} -->

<!--
@dependency-start
contract skill
responsibility Exposes agent-orchestration for runtime discovery.
upstream design ../../../agents/skills/agent-orchestration.md owner
@dependency-end
-->

# agent-orchestration

## Canonical Skill

Canonical workflow and policy: [agent-orchestration](../../../agents/skills/agent-orchestration.md).

## Tool Commands

<!-- skill-tool-commands:start -->
`python3 tools/agent_tools/skill_tool_commands.py show --skill agent-orchestration --format text`
<!-- skill-tool-commands:end -->

1. Read the canonical owner before applying this skill.
