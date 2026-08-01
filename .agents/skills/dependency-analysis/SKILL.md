---
name: dependency-analysis
description: "Use when checking, validating, or diagnosing repository dependency manifests, expanding code/header/search dependencies into a change-impact packet, or preparing repair-planning and subagent handoff context before editing, review, or closeout."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":1,"record_digest":"3f6fe5bc2d3b1c773b2519947907dc240368c17aba351bf42b5a531f82542d2a"} -->

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
