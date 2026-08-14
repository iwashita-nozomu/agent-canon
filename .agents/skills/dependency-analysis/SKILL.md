---
name: dependency-analysis
description: "Use when checking, validating, or diagnosing repository dependency manifests, expanding code/header/search dependencies into a change-impact packet, or preparing repair-planning and subagent handoff context before editing, review, or closeout."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":2,"record_digest":"de7f76a95e5b7637442b6582b93ce208c27ca4ebd1750d5b2b81f1294ad7b512"} -->

<!--
@dependency-start
contract skill
responsibility Exposes dependency-analysis for runtime discovery.
upstream design ../../../agents/skills/dependency-analysis.md owner
@dependency-end
-->

# dependency-analysis

## Canonical Skill

Canonical workflow and policy: [dependency-analysis](../../../agents/skills/dependency-analysis.md).

## Tool Commands

<!-- skill-tool-commands:start -->
`python3 tools/agent_tools/skill_tool_commands.py show --skill dependency-analysis --format text`
<!-- skill-tool-commands:end -->

1. Read the canonical owner before applying this skill.
