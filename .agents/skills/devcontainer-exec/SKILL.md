---
name: devcontainer-exec
description: "Use when an existing Dev Container needs targeted execution or validation through devcontainer exec, including a zsh shell, while preserving exact output and exit evidence."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":2,"record_digest":"c1ac9d75c56bf14b2a26a6a551fc1bf5c9f4aa3baaf7900e96e369d736156e8b"} -->

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
