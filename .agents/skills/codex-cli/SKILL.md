---
name: codex-cli
description: Use when the active agent is Codex and you need the repository-specific startup path, document order, and skill discovery path for local work.
---

# Codex CLI

1. Start in the repository root.
1. Read `AGENTS.md` first, then `agents/README.md`, then `agents/canonical/README.md`.
1. Read `agents/canonical/CODEX_WORKFLOW.md` to get the standard task flow before loading task-specific docs.
1. In the first work update, declare `workflow=<family>`, `skills=<...>`, `review=<...>`.
1. Prefer `$skill-name` when a user or parent agent wants explicit skill selection. Example: `$research-workflow`, `$paper-writing`.
1. If the runtime supports it, switch `/collab` to `Plan` before planning and use `/agent` to inspect configured subagents.
1. If `/agent` is unavailable, inspect `.codex/agents/*.toml` directly.
1. Use `.agents/skills/` as the project skill path.
1. For workflow selection, read `agents/TASK_WORKFLOWS.md`.
1. For artifact placement, read `agents/canonical/ARTIFACT_PLACEMENT.md`.
1. For run bootstrap, use `python3 scripts/agent_tools/bootstrap_agent_run.py --task ... --owner ... --workspace-root "$PWD" --enable scheduler --enable schedule_reviewer`.
