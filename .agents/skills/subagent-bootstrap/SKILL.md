---
name: subagent-bootstrap
description: "Use when a task needs specialist delegation, run-bundle bootstrap, explicit stage subagents, or Codex implementation routing."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":1,"record_digest":"e03c7daff99431e50b41b701048390daeab361809dea81ec690592b5a612aa15"} -->

<!--
@dependency-start
contract skill
responsibility Exposes subagent-bootstrap for runtime discovery.
upstream design ../../../agents/skills/subagent-bootstrap.md owner
@dependency-end
-->

# subagent-bootstrap

## Canonical Skill

Canonical workflow and policy: [subagent-bootstrap](../../../agents/skills/subagent-bootstrap.md).

## Tool Commands

<!-- skill-tool-commands:start -->
`python3 tools/agent_tools/skill_tool_commands.py show --skill subagent-bootstrap --format text`
<!-- skill-tool-commands:end -->

1. Read the canonical owner before applying this skill.
