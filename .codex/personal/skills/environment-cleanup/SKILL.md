---
name: environment-cleanup
description: "Use when environment dependencies or runtime capabilities need cleanup through dependency-design and environment-maintenance with version, scope, security, and rollback evidence."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":3,"record_digest":"ec65a78e97f58e86504807af6e3989d760b83bfce727019e503e94192a773065"} -->

<!--
@dependency-start
contract skill
responsibility Exposes environment-cleanup for runtime discovery.
upstream design ../../../../agents/skills/environment-cleanup.md owner
@dependency-end
-->

# environment-cleanup

## Canonical Skill

Canonical workflow and policy: [environment-cleanup](../../../../agents/skills/environment-cleanup.md).

## Tool Commands

<!-- skill-tool-commands:start -->
`python3 tools/agent/skills/skill_tool_commands.py show --skill environment-cleanup --format text`
<!-- skill-tool-commands:end -->

1. Read the canonical owner before applying this skill.
