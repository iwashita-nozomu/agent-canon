---
name: codex-task-workflow
description: "Use when Codex needs a context-independent execution path for a repository task, from intake and workflow selection through artifact placement, implementation, validation, and closeout."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":1,"record_digest":"8dc7dd846b68b7ed8281f1d80d07f0985aed7385dfd32a5b32a3d8cd1562f38c"} -->

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
