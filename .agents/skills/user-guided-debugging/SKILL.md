---
name: user-guided-debugging
description: Use when the user explicitly asks to debug, repair, or refactor one issue at a time with visible problem statements before each edit and a next-issue prompt after each scoped fix.
---
<!--
@dependency-start
contract skill
responsibility Documents User-Guided Debugging for this repository.
upstream design ../../../agents/skills/user-guided-debugging.md human-facing skill canon
upstream design ../../../agents/canonical/skills.md skill canon registry
@dependency-end
-->


# User-Guided Debugging

## Tool Commands

<!-- skill-tool-commands:start -->
Use the command packet before applying this skill's workflow:

```bash
python3 tools/agent_tools/skill_tool_commands.py show --skill user-guided-debugging --format text
```

Execute the required and task-matching conditional commands that the packet prints.
<!-- skill-tool-commands:end -->


1. Read `agents/skills/user-guided-debugging.md`.
1. Select exactly one next target issue.
1. Before editing, show the user:
   - target object or path
   - concrete problem
   - evidence or failing code path
   - intended repair surface
1. Do not patch before that problem statement is visible in chat.
1. Keep the patch scoped to the displayed target unless evidence moves the root cause; if it moves, show the new problem statement before editing.
1. Do not run tests, smoke runs, lint, docs checks, benchmarks, or other validation commands in this cadence unless the user explicitly asks for that execution after the patch.
1. Report the patch result, state that validation was not run when it was skipped, and present the next concrete issue.
1. Use this skill only when the user explicitly asks for this cadence; do not make it an `agent-orchestration` default.
