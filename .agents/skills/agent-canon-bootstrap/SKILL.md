---
name: agent-canon-bootstrap
description: "Use when AgentCanon's shared Python, Rust, or LSP tool runtime must be installed, started, targeted, inspected, updated, evaluated, or removed; project builds and tests remain in the project Docker/test-runner plane."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":2,"record_digest":"14f0632631e50a6211fa476922c1374971d2b1f947ee9678412452bb3acaaa35"} -->

<!--
@dependency-start
contract skill
responsibility Exposes agent-canon-bootstrap for runtime discovery.
upstream design ../../../agents/skills/agent-canon-bootstrap.md owner
@dependency-end
-->

# agent-canon-bootstrap

## Canonical Skill

Canonical workflow and policy: [agent-canon-bootstrap](../../../agents/skills/agent-canon-bootstrap.md).

## Tool Commands

<!-- skill-tool-commands:start -->
`python3 tools/agent_tools/skill_tool_commands.py show --skill agent-canon-bootstrap --format text`
<!-- skill-tool-commands:end -->

1. Read the canonical owner before applying this skill.
