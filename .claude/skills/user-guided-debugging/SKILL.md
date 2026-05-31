---
name: user-guided-debugging
description: Use when the user explicitly asks to debug or repair one issue at a time with visible problem statements before each edit and a next-issue prompt after each validated fix.
---
<!--
@dependency-start
responsibility Documents User-Guided Debugging for this repository.
upstream design ../../../agents/skills/user-guided-debugging.md human-facing skill canon
upstream design ../../../agents/canonical/skills.md skill canon registry
@dependency-end
-->


# User-Guided Debugging

1. Read `agents/skills/user-guided-debugging.md`.
1. Select exactly one next target issue.
1. Before editing, show the user:
   - target object or path
   - concrete problem
   - evidence or failing code path
   - intended repair surface
1. Do not patch before that problem statement is visible in chat.
1. Keep the patch scoped to the displayed target unless evidence moves the root cause; if it moves, show the new problem statement before editing.
1. Run local validation for the repaired target.
1. Report the validation result and present the next concrete issue.
1. Use this skill only when the user explicitly asks for this cadence; do not make it an `agent-orchestration` default.
