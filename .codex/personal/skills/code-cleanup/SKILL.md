---
name: code-cleanup
description: "Use when public or module code cleanup must be bounded by responsibility and reachability, then passed through dependency-analysis, refactor-loop, and change-review."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":3,"record_digest":"64122e4ddc4773927836342ae9884b3e0761fe25a3b2f6a2e9dd3404a5060c5d"} -->

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
