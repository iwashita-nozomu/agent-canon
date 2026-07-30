---
name: worktree-health
description: "Use this skill to review current checkout authority, run-bundle drift, legacy worktree cleanup evidence, and cleanup readiness."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":1,"record_digest":"57f7e694bc23672c5fba0e883c968548978f9d2bc115b0ae3059c057fac84e72"} -->

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
