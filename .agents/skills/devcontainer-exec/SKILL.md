---
name: devcontainer-exec
description: "Use when an existing Dev Container needs targeted execution or validation through devcontainer exec, including a zsh shell, while preserving exact output and exit evidence."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":2,"record_digest":"b185ff936aeb0e4fbc759f17165408c1a69ef1dda4562222b1120a5d74bc5c44"} -->

<!--
@dependency-start
contract skill
responsibility Exposes devcontainer-exec for runtime discovery.
upstream design ../../../agents/skills/devcontainer-exec.md owner
@dependency-end
-->

# devcontainer-exec

## Canonical Skill

Canonical workflow and policy: [devcontainer-exec](../../../agents/skills/devcontainer-exec.md).

## Tool Commands

<!-- skill-tool-commands:start -->
`python3 tools/agent_tools/skill_tool_commands.py show --skill devcontainer-exec --format text`
<!-- skill-tool-commands:end -->

1. Read the canonical owner before applying this skill.
