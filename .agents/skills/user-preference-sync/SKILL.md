---
name: user-preference-sync
description: Use when memory/USER_PREFERENCES.md should be distilled into stable AGENTS.md preferences without carrying over task-local instructions.
---
<!--
@dependency-start
contract skill
responsibility Documents User Preference Sync for this repository.
upstream design ../../../agents/canonical/skills.md skill canon registry
@dependency-end
-->


# User Preference Sync

## Tool Commands

<!-- skill-tool-commands:start -->
Use the command packet before applying this skill's workflow:

```bash
python3 tools/agent_tools/skill_tool_commands.py show --skill user-preference-sync --format text
```

Execute the required and task-matching conditional commands that the packet prints.
<!-- skill-tool-commands:end -->


1. Read `agents/skills/user-preference-sync.md`.
1. Read `AGENTS.md` and `memory/USER_PREFERENCES.md`.
1. Separate durable repo-wide preferences from task-local instructions.
1. Promote only repeated and stable items into `AGENTS.md`.
1. Keep rationale, examples, and volatile observations in `memory/USER_PREFERENCES.md` unless they are project-specific notes that belong under repo-local `notes/themes/`.
