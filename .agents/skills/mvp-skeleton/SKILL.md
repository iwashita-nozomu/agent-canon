---
name: mvp-skeleton
description: Use when creating, scaffolding, planning, or implementing an MVP, prototype, runnable vertical slice, product skeleton, v0, or thin vertical slice and the agent must prevent overbuilding. Trigger for MVP作成, プロトタイプ, 骨格だけ, core runnable path, thin vertical slice, scope creep, over-polish, and cases where early implementation is getting unnecessary UI, architecture, features, or tests.
---
<!--
@dependency-start
contract skill
responsibility Documents MVP Skeleton runtime skill for this repository.
upstream design ../../../agents/skills/mvp-skeleton.md documents the human-facing MVP skeleton workflow
downstream design ../../../agents/skills/catalog.yaml catalogs this public skill
@dependency-end
-->

# MVP Skeleton

## Tool Commands

<!-- skill-tool-commands:start -->
Use the command packet before applying this skill's workflow:

```bash
python3 tools/agent_tools/skill_tool_commands.py show --skill mvp-skeleton --format text
```

Execute the required and task-matching conditional commands that the packet prints.
<!-- skill-tool-commands:end -->


1. Read `agents/skills/mvp-skeleton.md`.
1. Before editing, write a compact MVP contract in working notes, a run bundle, or the user-facing plan:
   - `core_user`: who uses the skeletal slice
   - `core_loop`: one input-to-useful-output path
   - `success_signal`: observable result that proves the core loop
   - `runtime_floor`: local run or inspection path that exercises the loop
   - `stop_line`: tempting work that must be deferred
1. Classify every candidate feature as `required`, `stub`, or `defer`; choose `defer` when uncertain.
1. Keep only the `required` items that are necessary for one end-to-end path.
1. Prefer one vertical slice over reusable infrastructure, extra workflows, broad abstractions, and generalized services.
1. Stub auth, external services, payments, imports, analytics, admin tools, notifications, search, exports, persistence, and deployment unless the core loop specifically depends on them.
1. For frontend work, make the entry screen the usable product surface rather than a landing page unless the user explicitly asked for a landing page.
1. Add a smoke check that proves the MVP path runs.
1. Stop when the core runnable path is available and report:
   - core loop implemented
   - run or inspection path
   - smoke check performed
   - deferred list capped at five items
1. Treat the deferred list as success evidence and scope control.
