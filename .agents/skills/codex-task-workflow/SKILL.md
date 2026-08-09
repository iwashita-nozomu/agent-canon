---
name: codex-task-workflow
description: "Use when Codex needs a context-independent execution path for a repository task, from intake and workflow selection through artifact placement, implementation, validation, and closeout."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":2,"record_digest":"b2e8869eed382c3d9de861ced722616a07dd13498554dbd8045c2fcdcbe0d916"} -->

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
