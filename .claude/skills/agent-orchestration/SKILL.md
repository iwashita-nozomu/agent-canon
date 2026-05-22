---
name: agent-orchestration
description: Mandatory first skill for repository tasks. Use before selecting workflow family, skills, review roles, subagents, model/team policy, runtime entrypoints, run bundles, or Codex/Claude/Copilot routing.
---
<!--
@dependency-start
responsibility Documents Agent Orchestration for this repository.
upstream design ../../../agents/canonical/skills.md skill canon registry
upstream design ../../../agents/workflows/hypothesis-validation-workflow.md analysis-first overlay routing
@dependency-end
-->


# Agent Orchestration

1. Read `agents/skills/agent-orchestration.md`.
1. Read `agents/TASK_WORKFLOWS.md`, `agents/canonical/CLI_ENTRYPOINTS.md`, and `agents/canonical/CODEX_SUBAGENTS.md` before making any routing choice.
1. For repository tasks, keep convention verification in the execution path: include `python3 tools/agent_tools/check_convention_compliance.py` in the selected workflow closeout gates instead of restating every mechanical convention inside this prompt.
1. First classify the request into one of these modes:
   - `repo-changing execution`: the user is asking to edit the repo, start the run, or produce a concrete kickoff command now
   - `routing-only/advisory`: the user only wants workflow/skill/review guidance and is not yet starting repo edits
1. Choose exactly one primary workflow family from `agents/TASK_WORKFLOWS.md`. If a task id is known, treat the task-catalog mapping as the ground truth family.
1. Build the public skill set in this order:
   - put `$agent-orchestration` first
   - preserve every user-provided `$skill-name`
   - for `repo-changing execution`, add `$codex-task-workflow`
   - add `$subagent-bootstrap` only when the task is Shared canon, Large delivery, high-risk, multi-step, or explicitly uses subagents
   - add the minimal task-shape skill that matches the work:
     - research-backed implementation, benchmark, or external-research change -> `$research-workflow`
     - README, workflow, guide, migration, or other long reader-facing docs -> `$long-form-writing`
     - submission paper or thesis-chapter draft -> `$paper-writing`
     - broader academic or scholarly-note writing that is not primarily a paper draft -> `$academic-writing`
     - large refactor -> `$behavior-preserving-refactor`
     - environment / CI / Docker / dependency work -> `$environment-maintenance`
     - repo-wide workflow/tooling rearchitecture -> `$comprehensive-development`
     - iterative tuning or backlog-driven empirical improvement -> `$adaptive-improvement-loop`
     - code-improvement hypothesis, cause analysis, hypothesis validation, fix-surface selection, or multi-candidate comparison -> `$dependency-analysis` plus `agents/workflows/hypothesis-validation-workflow.md` as an overlay
     - Markdown file edits, docs lint/link/heading repair, docs-check failures, or Markdown style drift -> `$md-style-check`
     - accumulated skill/tool/workflow/hook/eval log analysis, routing misses, selection gaps, or weak-skill diagnosis -> `$agent-log-analysis`
     - user/reviewer feedback about agent behavior, repeated routing misses, recurrence prevention, task retrospectives, or agent-side memory updates -> `$agent-learning`
   - do not add unrelated family skills just because they are nearby in the catalog
1. Keep the advisory branch narrow. If the request is `routing-only/advisory`, do not silently escalate into full repo-changing kickoff, run-bundle bootstrap, repo MCP tools, `check_mcp_inventory.py`, shell / GitHub checks, or repo-changing-only skills. Ordinary consultation, brainstorming, and explanation-only turns stay conversational until the user asks to inspect repo state, edit files, run validation, process PRs/issues, check CI, or execute implementation work.
1. Choose the starter command with explicit precedence:
   - if the request is `repo-changing execution`, or the user asks for the startup command / run bundle, prefer `python3 tools/agent_tools/bootstrap_agent_run.py --task "<task>" --task-id <T*> --owner codex --workspace-root "$PWD"`
   - use `python3 tools/agent_tools/task_start.py --task "<task>" --task-id <T*> --owner codex --workspace-root "$PWD"` only for routing-only starter guidance when no run bundle is being created yet
1. Emit a family-appropriate output set:
   - one chosen `workflow=<family>`
   - `skills=<...>` with `$agent-orchestration` first, preserved explicit skills, and only the needed additions
   - `review=<...>` plus the minimal specialist / reviewer stack that matches that family
   - the starter command when the scenario asks for kickoff guidance
   - for execution tasks, the first work-update declaration `workflow=<family>`, `skills=<...>`, `review=<...>`
1. For PR-producing repository tasks, carry that first routing declaration into the PR body, run bundle, or linked comment with `skills=$agent-orchestration` first and the result of `python3 tools/agent_tools/route.py --prompt "<user request>" --format json` when prompt-derived routing is relevant.
1. Mention Codex implementation routing only when implementation is in scope. Read `agents/canonical/CODEX_SUBAGENTS.md` before assigning agents.
1. For Routine docs or Focused code, parent-direct implementation is allowed after the risk class and check matrix are fixed. For subagent implementation, talk about `spark_worker` only after bootstrap or task-start output exposes `IMPLEMENTATION_CODEX_AGENTS`. Use `spark_worker` first only for approved, design-traced slices that are one file or one abstraction unit, public interface unchanged, no dependency change, no specification interpretation, and locally testable; use `worker` when design interpretation, broad architecture, scope judgment, or conflict resolution is required.
1. Do not route detailed design, review, or final judgment to `spark_worker`.
