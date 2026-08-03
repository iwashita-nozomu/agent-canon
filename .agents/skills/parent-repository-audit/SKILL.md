---
name: parent-repository-audit
description: "Use when auditing an AgentCanon-consuming parent repository across structure, ownership, environment, dependencies, code and types, OOP, tests, docs and design trace, CI/hooks/skills, templates, or Git/PR lifecycle, with owner-routed repair and finding closure."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":1,"record_digest":"c91008546bcceb9445437f6f2a62263f298740e119cec388176dc5302a2d520e"} -->

<!--
@dependency-start
contract skill
responsibility Exposes parent-repository-audit for runtime discovery.
upstream design ../../../agents/skills/parent-repository-audit.md owner
@dependency-end
-->

# parent-repository-audit

## Canonical Skill

Canonical workflow and policy: [parent-repository-audit](../../../agents/skills/parent-repository-audit.md).

## Tool Commands

<!-- skill-tool-commands:start -->
`python3 tools/agent_tools/skill_tool_commands.py show --skill parent-repository-audit --format text`
<!-- skill-tool-commands:end -->

1. Read the canonical owner before applying this skill.
