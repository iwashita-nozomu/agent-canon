---
name: subagent-bootstrap
description: "Use when a task needs specialist delegation, run-bundle bootstrap, explicit stage subagents, or Codex implementation routing."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":2,"record_digest":"f92e2644deef80c3d4d37941f3316abb5a34f41c195b4ab74e9f6f632f12567e"} -->

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
