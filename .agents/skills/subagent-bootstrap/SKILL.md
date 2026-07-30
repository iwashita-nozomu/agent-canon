---
name: subagent-bootstrap
description: "Use when a task needs specialist delegation, run-bundle bootstrap, explicit stage subagents, or Codex implementation routing."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":1,"record_digest":"3c2f4a2bcc2b60d1c1a60f760e66095c61b2ff2dc0412a2f7152da40f0c7c7b0"} -->

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
