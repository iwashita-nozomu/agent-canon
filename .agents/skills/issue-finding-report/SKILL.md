---
name: issue-finding-report
description: "Use when creating, splitting, merging, re-parenting, reopening, or superseding Issues by owner, decision, mechanism, validation, and completion responsibility; investigates cause hypotheses without overclaiming, preserves unique clauses, and can also convert accumulated runtime evidence into durable AgentCanon Issues."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":2,"record_digest":"8dc5a20e683c0ae92d1883f5a9b906f08459784368e00fedfa19605dfeb0bc51"} -->

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
