---
name: worktree-health
description: "Use this skill to review current checkout authority, run-bundle drift, legacy worktree cleanup evidence, and cleanup readiness."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":2,"record_digest":"dd9f01ddd4753896336df441d4fcb38568de32160be90279f67c9c4bc0a505ca"} -->

<!--
@dependency-start
contract skill
responsibility Exposes worktree-health for runtime discovery.
upstream design ../../../agents/skills/worktree-health.md owner
@dependency-end
-->

# worktree-health

## Canonical Skill

Canonical workflow and policy: [worktree-health](../../../agents/skills/worktree-health.md).

## Tool Commands

<!-- skill-tool-commands:start -->
`python3 tools/agent_tools/skill_tool_commands.py show --skill worktree-health --format text`
<!-- skill-tool-commands:end -->

1. Read the canonical owner before applying this skill.
