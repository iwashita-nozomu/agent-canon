---
name: agent-canon-bootstrap
description: "Use when AgentCanon's shared Python, Rust, or LSP tool runtime must be installed, started, targeted, inspected, updated, evaluated, or removed; project builds and tests remain in the project Docker/test-runner plane."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":3,"record_digest":"a72922b1875c6c1ca2cd7e4632c09a36cf504439469833c2cb2be509de74d65a"} -->

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
