---
name: code-cleanup
description: "Use when public or module code cleanup must be bounded by responsibility and reachability, then passed through dependency-analysis, refactor-loop, and change-review."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":3,"record_digest":"97fb021afd6c4d4484f6c02b5f2e8feee9923f34281655b0db70a820198ca8e2"} -->

<!--
@dependency-start
contract skill
responsibility Exposes code-cleanup for runtime discovery.
upstream design ../../../../agents/skills/code-cleanup.md owner
@dependency-end
-->

# code-cleanup

## Canonical Skill

Canonical workflow and policy: [code-cleanup](../../../../agents/skills/code-cleanup.md).

## Tool Commands

<!-- skill-tool-commands:start -->
`python3 tools/agent/skills/skill_tool_commands.py show --skill code-cleanup --format text`
<!-- skill-tool-commands:end -->

1. Read the canonical owner before applying this skill.
