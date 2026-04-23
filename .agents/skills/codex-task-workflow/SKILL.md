---
name: codex-task-workflow
description: Use when Codex needs a context-independent execution path for a repository task, from intake and workflow selection through artifact placement, implementation, validation, and closeout.
---

# Codex Task Workflow

1. Read `agents/canonical/CODEX_WORKFLOW.md`.
1. On a clean worktree, run `make agent-canon-ensure-latest` before planning or implementation; if dirty, record why it is blocked and rerun after commit or stash.
1. Sweep `documents/`, `notes/`, `references/`, and local implementation directories before planning or implementation.
1. Classify the task with `agents/TASK_WORKFLOWS.md` before touching files.
1. In the first work update, declare `workflow=<family>`, `skills=<...>`, `review=<...>`.
1. When skills are explicitly named in the task or handoff, use `$skill-name` notation and preserve it in `skills=<...>`.
1. During requirements, resolve avoidable ambiguity from notes, guardrails, documents, prior logs, and local code or tests before asking the user; record the sweep and evidence in `user_request_contract.md`.
1. Keep `unknown_or_open_question` out of active must-do, must-not-do, and completion-evidence clauses; move remaining unknowns to deferred or escalation entries after the sweep.
1. For repo-editing tasks, bootstrap subagents before implementation with `python3 tools/agent_tools/bootstrap_agent_run.py ... --enable scheduler --enable schedule_reviewer`, and keep the plan reviewer, detailed design reviewer, and document flow reviewer separate.
1. Use `agents/canonical/ARTIFACT_PLACEMENT.md` before creating task-facing documents.
1. Load only the minimal extra skills the task needs; long-form docs add `long-form-writing`, submission papers or thesis-chapter drafts add `paper-writing`, broader academic or scholarly-note writing adds `academic-writing`, and the required notation/logic/citation reviewers follow that writing skill choice.
1. If the task needs explicit handoff or specialist roles, bootstrap `reports/agents/<run-id>/` first.
1. Update canonical docs before runtime entrypoints when both are affected.
1. Before implementation, read the approved `design_brief.md` `Implementation Source Packet` and `Design-To-Implementation Trace`; cite the design artifact path, design section, test-plan item, and user-request clause IDs for each changed slice.
1. If the design trace is missing or conflicts with repo docs or code, return to detailed design review instead of editing from chat context.
1. For fully design-traced, low-risk implementation slices, use `spark_worker` first and `worker` as fallback; keep requirements, design, review, and scope judgment off Spark.
1. Treat chunks, slices, checkpoints, and subpasses as internal progress only; continue until all planned work units, active clauses, final review, validation, closeout gate, commit, and push are complete.
1. Validate with `make ci-quick` first and escalate to broader checks only when needed.
