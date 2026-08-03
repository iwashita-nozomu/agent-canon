---
name: user-preference-sync
description: "Use when memory/USER_PREFERENCES.md should be distilled into stable AGENTS.md preferences without carrying over task-local instructions."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":1,"record_digest":"ee61a196589de57983d10dddf5274dc617d45378a734494315abdc31bfbe6af7"} -->

<!--
@dependency-start
contract skill
responsibility Exposes user-preference-sync for runtime discovery.
upstream design ../../../agents/skills/user-preference-sync.md owner
@dependency-end
-->

# user-preference-sync

## Canonical Skill

Canonical workflow and policy: [user-preference-sync](../../../agents/skills/user-preference-sync.md).

## Tool Commands

<!-- skill-tool-commands:start -->
`python3 tools/agent_tools/skill_tool_commands.py show --skill user-preference-sync --format text`
<!-- skill-tool-commands:end -->

1. Read the canonical owner before applying this skill.
