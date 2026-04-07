---
name: agent-orchestration
description: Use when you need to choose a workflow family, route work across roles, or align Codex, Claude, and Copilot entrypoints with the same canonical docs.
---

# Agent Orchestration

1. Start from `agents/TASK_WORKFLOWS.md`.
1. Choose one workflow family instead of inventing a one-off process.
1. For repo-editing tasks, keep the canonical stage order: requirements, research, execution plan, plan review, detailed design, detailed design review, document flow review, implementation.
1. Use `agents/COMMUNICATION_PROTOCOL.md` for handoff and review structure.
1. Use `agents/canonical/ARTIFACT_PLACEMENT.md` before creating new task-facing documents.
1. Use `agents/canonical/CLI_ENTRYPOINTS.md` when a runtime-specific command or subagent decision matters.
1. Keep human-maintained canon in `agents/`.
1. Keep runtime entrypoints thin: `AGENTS.md`, `CLAUDE.md`, `.github/copilot-instructions.md`.
