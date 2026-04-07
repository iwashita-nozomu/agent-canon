---
name: codex-task-workflow
description: Use when Codex needs a context-independent execution path for a repository task, from intake and workflow selection through artifact placement, implementation, validation, and closeout.
---

# Codex Task Workflow

1. Read `agents/canonical/CODEX_WORKFLOW.md`.
1. Classify the task with `agents/TASK_WORKFLOWS.md` before touching files.
1. For repo-editing tasks, bootstrap subagents before implementation and keep the plan reviewer, detailed design reviewer, and document flow reviewer separate.
1. Use `agents/canonical/ARTIFACT_PLACEMENT.md` before creating task-facing documents.
1. Load only the minimal extra skills the task needs; long-form docs should add `long-form-writing`.
1. If the task needs explicit handoff or specialist roles, bootstrap `reports/agents/<run-id>/` first.
1. Update canonical docs before runtime entrypoints when both are affected.
1. Validate with `make ci-quick` first and escalate to broader checks only when needed.
