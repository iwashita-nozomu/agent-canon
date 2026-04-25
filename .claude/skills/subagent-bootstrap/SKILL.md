---
name: subagent-bootstrap
description: Use when a task needs specialist delegation, run-bundle bootstrap, explicit stage subagents, or Codex implementation routing.
---
<!--
@dependency-start
@dependency-end
-->


# Subagent Bootstrap

1. Read `agents/skills/subagent-bootstrap.md`.
1. Read `agents/canonical/CODEX_SUBAGENTS.md`.
1. For repo-changing tasks, create or inspect a run bundle before implementation.
1. Use `--task-id` so `agents/task_catalog.yaml` expands default specialists and review packs.
1. Keep requirements review, plan review, detailed design review, and document flow review as separate agents.
1. Check the command output for `IMPLEMENTATION_CODEX_AGENTS`.
1. If `IMPLEMENTATION_CODEX_AGENTS` starts with `spark_worker,worker`, send approved, design-traced, low-risk implementation slices to `spark_worker` first.
1. Send broad implementation, design interpretation, conflict resolution, or architecture-sensitive work to `worker`.
1. Use one writer per worktree. If multiple writers are necessary, split worktrees before implementation.
