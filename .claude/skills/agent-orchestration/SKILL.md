---
name: agent-orchestration
description: Use when selecting workflow family, skills, review roles, runtime entrypoints, and Codex/Claude/Copilot routing before execution.
---

# Agent Orchestration

1. Read `agents/skills/agent-orchestration.md`.
1. Read `agents/TASK_WORKFLOWS.md`, `agents/canonical/CLI_ENTRYPOINTS.md`, and `agents/canonical/CODEX_SUBAGENTS.md` before making any routing choice.
1. First classify the request into one of these modes:
   - `repo-changing execution`: the user is asking to edit the repo, start the run, or produce a concrete kickoff command now
   - `routing-only/advisory`: the user only wants workflow/skill/review guidance and is not yet starting repo edits
1. Choose exactly one primary workflow family from `agents/TASK_WORKFLOWS.md`. If a task id is known, treat the task-catalog mapping as the ground truth family.
1. Build the public skill set in this order:
   - preserve every user-provided `$skill-name`
   - for `repo-changing execution`, add `$codex-task-workflow` and `$subagent-bootstrap`
   - add the minimal task-shape skill that matches the work:
     - research-backed implementation, benchmark, or external-research change -> `$research-workflow`
     - README, workflow, guide, migration, or other long reader-facing docs -> `$long-form-writing`
     - submission paper or thesis-chapter draft -> `$paper-writing`
     - broader academic or scholarly-note writing that is not primarily a paper draft -> `$academic-writing`
     - large refactor -> `$behavior-preserving-refactor`
     - environment / CI / Docker / dependency work -> `$environment-maintenance`
     - repo-wide workflow/tooling rearchitecture -> `$comprehensive-development`
     - iterative tuning or backlog-driven empirical improvement -> `$adaptive-improvement-loop`
   - do not add unrelated family skills just because they are nearby in the catalog
1. Keep the advisory branch narrow. If the request is `routing-only/advisory`, do not silently escalate into full repo-changing kickoff, run-bundle bootstrap, or repo-changing-only skills.
1. Choose the starter command with explicit precedence:
   - if the request is `repo-changing execution`, or the user asks for the startup command / run bundle, prefer `python3 tools/agent_tools/bootstrap_agent_run.py --task "<task>" --task-id <T*> --owner codex --workspace-root "$PWD"`
   - use `python3 tools/agent_tools/task_start.py --task "<task>" --task-id <T*> --owner codex --workspace-root "$PWD"` only for routing-only starter guidance when no run bundle is being created yet
1. Emit a family-appropriate output set:
   - one chosen `workflow=<family>`
   - `skills=<...>` with preserved explicit skills and only the needed additions
   - `review=<...>` plus the minimal specialist / reviewer stack that matches that family
   - the starter command when the scenario asks for kickoff guidance
   - for execution tasks, the first work-update declaration `workflow=<family>`, `skills=<...>`, `review=<...>`
1. Mention Codex implementation routing only when implementation is in scope. Read `agents/canonical/CODEX_SUBAGENTS.md` before assigning agents.
1. For implementation, talk about `spark_worker` only after bootstrap or task-start output exposes `IMPLEMENTATION_CODEX_AGENTS`. Use `spark_worker` first only for approved, design-traced, low-risk slices; use `worker` when design interpretation, broad architecture, scope judgment, or conflict resolution is required.
1. Do not route detailed design, review, or final judgment to `spark_worker`.
