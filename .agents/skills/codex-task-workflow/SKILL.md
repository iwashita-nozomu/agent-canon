---
name: codex-task-workflow
description: "Use when Codex needs a context-independent execution path for a repository task, from intake and workflow selection through artifact placement, implementation, validation, and closeout."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":1,"record_digest":"85fce45c91e863162b77a31bfbe4ebf2fbf4b28e0ab6504308896aa005b16c09"} -->

<!--
@dependency-start
contract skill
responsibility Exposes codex-task-workflow for runtime discovery.
upstream design ../../../agents/skills/codex-task-workflow.md owner
@dependency-end
-->

# codex-task-workflow

## Canonical Skill

Canonical workflow and policy: [codex-task-workflow](../../../agents/skills/codex-task-workflow.md).

## Tool Commands

<!-- skill-tool-commands:start -->
`python3 tools/agent_tools/skill_tool_commands.py show --skill codex-task-workflow --format text`
<!-- skill-tool-commands:end -->

1. Read the canonical owner before applying this skill.
