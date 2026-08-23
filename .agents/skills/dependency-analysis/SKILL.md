---
name: dependency-analysis
description: "Use when checking, validating, or diagnosing repository dependency manifests, expanding code/header/search dependencies into a change-impact packet, or preparing repair-planning and subagent handoff context before editing, review, or closeout."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":2,"record_digest":"86080c335dd7c191d36c74be0015fa7b240a0aa46552618f3da03dbd74c6fde8"} -->

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
