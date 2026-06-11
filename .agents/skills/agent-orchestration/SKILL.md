---
name: agent-orchestration
description: Mandatory first skill for repository tasks. Use before selecting workflow family, skills, review roles, subagents, model/team policy, runtime entrypoints, or run bundles for Codex routing.
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
1. If the user explicitly asks for coding, implementation, or patch work to be delegated to subagents, treat that as explicit subagent implementation routing. Add `$subagent-bootstrap`; do not satisfy the request with read-only survey or review roles only.
1. First classify the request into one of these modes:
   - `repo-changing execution`: the user is asking to edit the repo, start the run, or produce a concrete kickoff command now
   - `routing-only/advisory`: the user only wants workflow/skill/review guidance and is not yet starting repo edits
1. For repo-changing execution where the implementation owner is not already fixed by an explicit path and source packet, run `agent-canon local-llm route-implementation-surface --request-file <request.txt> --format text` before selecting edit paths. Use `PRIMARY_SURFACE`, `PRIMARY_PATHS`, `FORBIDDEN_PATHS`, and `REQUIRED_PRE_EDIT_CHECKS` as the source packet seed, and pass `PRIMARY_PATHS` into write-capable `allowed_paths` plus `FORBIDDEN_PATHS` into `do_not_read`. If LocalLLM is unavailable, use the deterministic fallback output or record a router-unavailable blocker; do not select implementation paths from chat impression.
1. Before reading broad prose, scanning raw logs, or spawning a subagent, check whether a canonical tool already owns the needed judgment. If yes, call the tool first, trust its compact pass/finding output for the covered property, and read only the exact file slice needed to repair a finding.
1. Choose exactly one primary workflow family from `agents/TASK_WORKFLOWS.md`. If a task id is known, treat the task-catalog mapping as the ground truth family.
1. Resolve subagent concurrency as a hierarchy, not as one flat limit:
   - runtime hard ceiling: `.codex/config.toml` `[agents].max_threads`
   - runtime nesting ceiling: `.codex/config.toml` `[agents].max_depth`, currently `2` for one bounded child-subagent layer
   - workflow active budget and family default first-wave target: `agents/task_catalog.yaml` `workflow_families[].spawn_budget.active_subagents`
   - stage wave plan: owner-owned bounded waves within the active budget; parent may delegate a stage owner to spawn child subagents when the handoff packet fixes owner, input packet, expected output, write scope, validation route, and review gate
   - write-capable budget: `workflow_families[].spawn_budget.max_write_subagents`, which limits only writer agents with disjoint write scopes
   - Initial Intake Wave is the first responsibilities wave, not the total concurrent-subagent cap; if a multi-agent family starts with fewer than the family default target, record the rate-limit, blocked-role, irrelevant-role, or parent-direct reason in `schedule.md` / `workflow_monitoring.md`
   - generated `team_manifest.yaml` must preserve `run.spawn_budget.active_subagents`, `run.spawn_budget.max_write_subagents`, `run.spawn_budget.runtime_max_threads`, `run.spawn_budget.runtime_max_depth`, `run.delegated_spawn_policy`, and `run.write_scope_policy.max_write_subagents`
1. Build the public skill set in this order:
   - put `$agent-orchestration` first
   - preserve every user-provided `$skill-name`
   - for `repo-changing execution`, add `$codex-task-workflow`
   - add `$subagent-bootstrap` only when the task is Shared canon, Large delivery, high-risk, multi-step, or explicitly uses subagents
   - add the minimal task-shape skill that matches the work:
     - research-backed implementation, benchmark, or external-research change -> `$research-workflow`
     - nontrivial or substantive document creation/addition/revision where section order, reader path, claim support, source map, canonical route, or document responsibility changes -> `$prose-reasoning-graph` as the common structure-first graph/DSL gate; for typo/link/format-only edits, use `$md-style-check` and record why structure analysis was skipped
     - README, workflow, guide, migration, or other general explanatory reader-facing docs -> `$long-form-writing` as the DSL-to-prose projection adapter; do not select it by length alone
     - submission paper or thesis-chapter draft -> `$paper-writing`
     - broader academic or scholarly-note writing that is not primarily a paper draft -> `$academic-writing`
     - PR body, PR evidence comment, status update, decision brief, presentation narrative, PPT storyboard, or reader-facing report from tool, JSON/JSONL, hook, eval, checker, experiment, review, or audit evidence -> `$report-writing`; report output defaults to Markdown unless the user explicitly asks for HTML, browser view, dashboard, web page, or external browser publication; if PPT/deck is in scope, include a visual asset plan and slide-production workflow; if raw machine results are written or copied, also add `$result-artifact-writeout`
     - explicit HTML output, HTML report, browser-readable page, dashboard, local preview server, or external browser publication -> `$html-output`
     - explicit HTML experiment or Eval report -> `$html-experiment-report` plus `$html-output`
     - nontrivial report, experiment plan/report, Eval output, decision brief, presentation/PPT deck, HTML view, document, paper, or refactor structure; first figure/table/ponchi-e/slide/section/slice choice; source map; source-to-slide map; or invalid interpretation boundary -> `$structure-planning`
     - tool/checker/hook/static-analysis runs to discover problems, create finding packets, compare before/after impact, or feed implementation/refactor planning -> `$tool-finding-report`; if raw results are written, also add `$result-artifact-writeout`; if the output is reader-facing narrative, also add `$report-writing`; if that narrative has a nontrivial finding packet, priority policy, metric/count contract, or source map, also add `$structure-planning`
     - README, workflow, guide, migration, or specification docs keep their domain projection adapter; add `$report-writing` as an overlay when the document includes evidence-backed status, evaluation, audit, review, decision, or recommendation sections
     - large refactor -> `$refactor-loop`
     - directory layout, directory README responsibility, root view, path mapping, responsibility-scope map, or source-tree ownership refactor -> `$structure-refactor` plus `$refactor-loop`
     - expected AgentCanon repo structure, root view, `vendor/agent-canon/`, `.gitmodules`, or canonical path drift before an ordinary task -> `$structure-refactor` pre-task repair route; add `$agent-canon-update` for AgentCanon-owned root-view or submodule drift
     - environment / CI / Docker / dependency work -> `$environment-maintenance`
     - repo-wide workflow/tooling rearchitecture -> `$comprehensive-development`
     - iterative tuning or backlog-driven empirical improvement -> `$adaptive-improvement-loop`
     - optimizer, solver, preconditioner, gradient, Jacobian, Hessian, KKT, convergence, tolerance, numerical benchmark, or numerical-test diagnosis -> `$computational-optimization`
     - code-improvement hypothesis, cause analysis, hypothesis validation, fix-surface selection, multi-candidate comparison, change-impact packet creation, or repair-planning/subagent handoff context -> `$dependency-analysis` plus `agents/workflows/hypothesis-validation-workflow.md` as an overlay when a cause hypothesis is involved
     - Markdown file edits, docs lint/link/heading repair, Mermaid/math drift, formatter adjacent checks, `agent-canon docs`, docs-check failures, or Markdown style drift -> `$md-style-check`
     - accumulated skill/tool/workflow/hook/eval log analysis, routing misses, selection gaps, or weak-skill diagnosis -> `$agent-log-analysis`
     - AgentCanon source update, `vendor/agent-canon` submodule latest/pin update, root runtime view repair, parent AgentCanon update TODOs, or `make agent-canon-ensure-latest` / `tools/update_agent_canon.sh` routing -> `$agent-canon-update`; add `$agent-update-branch` only when a parent-repo `canon-pin` branch lane is needed
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
1. For Routine docs or Focused code, parent-direct implementation is allowed after the risk class and check matrix are fixed. If the user requested subagent coding delegation, parent-direct is a alternate route only after the write-capable subagent route is blocked and recorded. For subagent implementation, talk about `spark_worker` only after bootstrap or task-start output exposes `IMPLEMENTATION_CODEX_AGENTS`. Use `spark_worker` first only for approved slices derived from the Abstract Design Frame and design trace that are one file or one abstraction unit, public interface unchanged, no dependency change, no specification interpretation, and locally testable; use `worker` when design interpretation, broad architecture, scope judgment, or conflict resolution is required.
1. Do not use `explorer` or broad read-only review to re-check properties that a tool has already checked. Subagents receive compact tool artifacts and bounded finding paths; if the tool output is missing an abstraction needed for routing, extend or repair the tool contract instead of compensating with bulk prose reading.
1. Once requirements, bounded `allowed_paths`, write scope, validation plan, and tool-rejection preflight are fixed for an explicit subagent coding request, schedule or launch `spark_worker` / `worker` before adding more read-only waves. If runtime authorization or tool gates block the write-capable spawn, record `WRITE_SUBAGENT_AUTHORIZATION=required` or the gate-specific blocker in the run bundle instead of replacing implementation with more read-only analysis.
1. Do not route detailed design, review, or final judgment to `spark_worker`.
