---
name: agent-canon-update
description: "Use when updating standalone AgentCanon source, its bootstrap/runtime, skills, eval/archive route, or publishing a qualified AgentCanon branch and PR."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":3,"record_digest":"214940dc123ae456879039c4526ed15b44eaeb28c098ea2423f984a7a08b41b0"} -->

<!--
@dependency-start
contract skill
responsibility Exposes agent-canon-update for runtime discovery.
upstream design ../../../../agents/skills/agent-canon-update.md owner
@dependency-end
-->

# agent-canon-update

## Canonical Skill

Canonical workflow and policy: [agent-canon-update](../../../../agents/skills/agent-canon-update.md).

## Tool Commands

<!-- skill-tool-commands:start -->
`python3 tools/agent/skills/skill_tool_commands.py show --skill agent-canon-update --format text`
<!-- skill-tool-commands:end -->

1. Read the canonical owner before applying this skill.
