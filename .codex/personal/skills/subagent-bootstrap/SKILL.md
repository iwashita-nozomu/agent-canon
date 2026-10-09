---
name: subagent-bootstrap
description: "Use when a selected route needs child delegation or durable coordination/resumption."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":3,"record_digest":"abed0a7c9cb080aaf7190e7b93d0176e070367f6337737546f94d31d70833d49"} -->

<!--
@dependency-start
contract skill
responsibility Exposes subagent-bootstrap for runtime discovery.
upstream design ../../../../agents/skills/subagent-bootstrap.md owner
@dependency-end
-->

# subagent-bootstrap

## Canonical Skill

Canonical workflow and policy: [subagent-bootstrap](../../../../agents/skills/subagent-bootstrap.md).

## Tool Commands

<!-- skill-tool-commands:start -->
`python3 tools/agent/skills/skill_tool_commands.py show --skill subagent-bootstrap --format text`
<!-- skill-tool-commands:end -->

1. Read the canonical owner before applying this skill.
