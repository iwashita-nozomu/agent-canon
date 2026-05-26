---
name: subagent-bootstrap
description: Use when a task needs specialist delegation, run-bundle bootstrap, explicit stage subagents, or Codex implementation routing.
---
<!--
@dependency-start
responsibility Documents Subagent Bootstrap for this repository.
upstream design ../../../agents/canonical/skills.md skill canon registry
@dependency-end
-->


# Subagent Bootstrap

1. Read `agents/skills/subagent-bootstrap.md`.
1. Read `agents/canonical/CODEX_SUBAGENTS.md`.
1. For repo-changing tasks, create or inspect a run bundle before implementation.
1. For goal-driven repo-changing tasks, create a provisional run bundle and start read-only `requirements_organizer` / `explorer` before `/goal` is finalized when the exact objective is not yet fixed.
1. Keep write-capable implementation subagents blocked until `goal.md` is parseable, the Codex goal view is mirrored or queued, and Plan-mode evidence mapping exists.
1. If the active runtime requires explicit user authorization before `spawn_agent`, do not silently spawn even read-only pre-goal agents. Record the fan-out plan, handoff packets, and `PRE_GOAL_SUBAGENT_AUTHORIZATION=required` in the run bundle, then wait for or request authorization.
1. Use `--task-id` so `agents/task_catalog.yaml` expands default specialists and review packs.
1. Keep requirements review, plan review, detailed design review, and document flow review as separate agents.
1. Check the command output for `IMPLEMENTATION_CODEX_AGENTS`.
1. If `IMPLEMENTATION_CODEX_AGENTS` starts with `spark_worker,worker`, send approved, design-traced, low-risk implementation slices to `spark_worker` first.
1. Read `.codex/config.toml` `agents.model_policy` before choosing model / reasoning for a spawned role.
1. For repo inventory, tool drift survey, static validation triage, diff-local Python / C++ review, and machine-report summarization, prefer the Spark bucket from `.codex/config.toml` when explicit spawn authorization exists.
1. For bounded review, report traceability, and checklist-style review gates, prefer the mini review bucket from `.codex/config.toml` before escalating to frontier roles.
1. Treat a narrow implementation slice as `spark_worker` eligible only when it is one file or one abstraction unit, public interface unchanged, no dependency change, no specification interpretation, and locally testable.
1. If a project-defined Spark role fails because runtime tools conflict with its effort profile, retry as a fresh default subagent using the Spark bucket's `model` and `model_reasoning_effort` from `.codex/config.toml` before escalating to the parent or frontier bucket.
1. Send broad implementation, design interpretation, conflict resolution, or architecture-sensitive work to `worker`.
1. Use one writer per worktree. If multiple writers are necessary, split worktrees before implementation.
1. For each new user request, start fresh run-local subagents; do not `send_input` a new task into subagents from a previous request.
1. Include `team_manifest.yaml` `run.subagent_lifecycle_policy` in every subagent handoff prompt, especially `fresh_subagents_required: true` and `reuse_for_new_task: forbidden`.
1. Before closeout, close run-local subagents and record `subagents_closed=yes` plus `Subagent Lifecycle Evidence` in `closeout_gate.md`.
