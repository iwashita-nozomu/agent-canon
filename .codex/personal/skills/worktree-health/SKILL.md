---
name: worktree-health
description: "Use this skill to review current checkout authority, run-bundle drift, legacy worktree cleanup evidence, and cleanup readiness."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":3,"record_digest":"eaa67eab0a96cf5b12af59daf99f96040b069b436a5b9eff0ab29aac3b8b5a5b"} -->

<!--
@dependency-start
contract skill
responsibility Exposes worktree-health for runtime discovery.
upstream design ../../../../agents/skills/worktree-health.md owner
@dependency-end
-->

# worktree-health

## Canonical Skill

Canonical workflow and policy: [worktree-health](../../../../agents/skills/worktree-health.md).

## Tool Commands

<!-- skill-tool-commands:start -->
`python3 tools/agent/skills/skill_tool_commands.py show --skill worktree-health --format text`
<!-- skill-tool-commands:end -->

1. Read the canonical owner before applying this skill.
