---
name: issue-finding-report
description: "Use when creating, splitting, merging, re-parenting, reopening, or superseding Issues by owner, decision, mechanism, validation, and completion responsibility; investigates cause hypotheses without overclaiming, preserves unique clauses, and can also convert accumulated runtime evidence into durable AgentCanon Issues."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":2,"record_digest":"23cf9f89a62eccd08c0338b8b8b48904a31a1369bd393d1c0ff5a2a93886381e"} -->

<!--
@dependency-start
contract skill
responsibility Exposes issue-finding-report for runtime discovery.
upstream design ../../../agents/skills/issue-finding-report.md owner
@dependency-end
-->

# issue-finding-report

## Canonical Skill

Canonical workflow and policy: [issue-finding-report](../../../agents/skills/issue-finding-report.md).

## Tool Commands

<!-- skill-tool-commands:start -->
`python3 tools/agent_tools/skill_tool_commands.py show --skill issue-finding-report --format text`
<!-- skill-tool-commands:end -->

1. Read the canonical owner before applying this skill.
