---
name: start-repository
description: "Use when starting a repository from this template after clone, including project identity setup, source-free static-seed validation, and destination-remote setup without live AgentCanon integration."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":3,"record_digest":"b29bf55a4197462b08762d377cd91c2ed819653e3a6ce3bb402cad6f6aa4db63"} -->

<!--
@dependency-start
contract skill
responsibility Exposes start-repository for runtime discovery.
upstream design ../../../../agents/skills/start-repository.md owner
@dependency-end
-->

# start-repository

## Canonical Skill

Canonical workflow and policy: [start-repository](../../../../agents/skills/start-repository.md).

## Tool Commands

<!-- skill-tool-commands:start -->
`python3 tools/agent/skills/skill_tool_commands.py show --skill start-repository --format text`
<!-- skill-tool-commands:end -->

1. Read the canonical owner before applying this skill.
