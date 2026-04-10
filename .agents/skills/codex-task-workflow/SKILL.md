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
1. For repo-editing tasks, bootstrap subagents before implementation with `python3 tools/agent_tools/bootstrap_agent_run.py ... --enable scheduler --enable schedule_reviewer`, and keep the plan reviewer, detailed design reviewer, and document flow reviewer separate.
1. Use `agents/canonical/ARTIFACT_PLACEMENT.md` before creating task-facing documents.
1. Load only the minimal extra skills the task needs; long-form docs add `long-form-writing`, and academic papers or thesis chapters add `academic-writing` plus notation/logic review.
1. If the task needs explicit handoff or specialist roles, bootstrap `reports/agents/<run-id>/` first.
1. Update canonical docs before runtime entrypoints when both are affected.
1. Validate with `make ci-quick` first and escalate to broader checks only when needed.
