---
name: agent-canon-update
description: "Use when updating AgentCanon itself, refreshing a vendored vendor/agent-canon submodule pin, repairing AgentCanon root runtime views, applying AgentCanon update TODOs, or routing local AgentCanon source commits through a proper AgentCanon branch and PR before parent pin updates."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":1,"record_digest":"1eef0e037cfd3654eb9a8ed9e27086851917f25fbdd6bde7928913ec521c147c"} -->

<!--
@dependency-start
contract skill
responsibility Exposes agent-canon-update for runtime discovery.
upstream design ../../../agents/skills/agent-canon-update.md owner
@dependency-end
-->

# agent-canon-update

## Canonical Skill

Canonical workflow and policy: [agent-canon-update](../../../agents/skills/agent-canon-update.md).

## Tool Commands

<!-- skill-tool-commands:start -->
`python3 tools/agent_tools/skill_tool_commands.py show --skill agent-canon-update --format text`
<!-- skill-tool-commands:end -->

1. Read the canonical owner before applying this skill.
