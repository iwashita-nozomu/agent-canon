---
name: agent-orchestration
description: Use when selecting workflow family, skills, review roles, runtime entrypoints, and Codex/Claude/Copilot routing before execution.
---

# Agent Orchestration

1. Read `agents/skills/agent-orchestration.md`.
1. Read `agents/TASK_WORKFLOWS.md` and choose one primary workflow family.
1. Read `agents/skills/README.md` and choose the minimal public skill set; preserve user-provided `$skill-name` entries.
1. For repo-changing tasks, include `$codex-task-workflow` and `$subagent-bootstrap` in the declared skill set.
1. Read `agents/canonical/CODEX_SUBAGENTS.md` before assigning Codex subagents.
1. Use `python3 tools/agent_tools/task_start.py --task "<task>" --task-id <T*> --owner codex --workspace-root "$PWD"` when a task id is known.
1. Use `python3 tools/agent_tools/bootstrap_agent_run.py --task "<task>" --task-id <T*> --owner codex --workspace-root "$PWD"` when a run bundle is needed directly.
1. Declare `workflow=<family>`, `skills=<...>`, and `review=<...>` in the first work update.
1. For implementation, prefer `spark_worker` first only for approved, design-traced, low-risk slices; use `worker` when design interpretation, broad architecture, or conflict resolution is required.
