---
name: agent-canon-bootstrap
description: "Use when AgentCanon's shared Python, Rust, or LSP tool runtime must be installed, started, targeted, inspected, updated, evaluated, or removed; project builds and tests remain in the project Docker/test-runner plane."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":3,"record_digest":"5e6e031e6cff6fc4df35d87d018c30a88ccf3e2360426edd260b7c6aa07354fc"} -->

<!--
@dependency-start
contract skill
responsibility Exposes agent-canon-bootstrap for runtime discovery.
upstream design ../../../../agents/skills/agent-canon-bootstrap.md owner
@dependency-end
-->

# agent-canon-bootstrap

## Canonical Skill

Canonical workflow and policy: [agent-canon-bootstrap](../../../../agents/skills/agent-canon-bootstrap.md).

## Tool Commands

<!-- skill-tool-commands:start -->
`python3 tools/agent/skills/skill_tool_commands.py show --skill agent-canon-bootstrap --format text`
<!-- skill-tool-commands:end -->

1. Read the canonical owner before applying this skill.
