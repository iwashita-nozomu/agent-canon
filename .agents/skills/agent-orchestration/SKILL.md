---
name: agent-orchestration
description: Mandatory routing skill for repository tasks. Use before selecting workflow family, skills, review roles, subagents, model/team policy, runtime entrypoints, or run bundles for Codex routing.
---
<!--
@dependency-start
contract skill
responsibility Documents Agent Orchestration for this repository.
upstream design ../../../agents/canonical/skills.md skill canon registry
upstream design ../../../agents/workflows/hypothesis-validation-workflow.md analysis-prioritized overlay routing
upstream design ../../../agents/COMMUNICATION_PROTOCOL.md pre-edit investigation and fresh subagent context packets
@dependency-end
-->


# Agent Orchestration

## Reader Map

- Purpose: runtime skill for mandatory repository-task routing before choosing
  workflow family, active skills, roles, reviews, or run bundles.
- Use When: any repo task needs routing, implementation ownership, subagent
  policy, review policy, or runtime entrypoint selection.
- Tool Commands: run this skill's command packet first, then the required
  canonical `agents/skills/agent-orchestration.md` read.
- Boundary: this runtime shim routes and records evidence; task execution stays
  with the selected workflow and task-shape skills.

## Tool Commands

<!-- skill-tool-commands:start -->
Use the command packet before applying this skill's workflow:

```bash
python3 tools/agent_tools/skill_tool_commands.py show --skill agent-orchestration --format text
```

Execute the required and task-matching conditional commands that the packet prints.
<!-- skill-tool-commands:end -->


1. Read `agents/skills/agent-orchestration.md`.
1. Read `agents/TASK_WORKFLOWS.md`, `agents/canonical/CLI_ENTRYPOINTS.md`, and `agents/canonical/CODEX_SUBAGENTS.md` before making any routing choice.
1. For repository tasks, keep convention verification in the execution path: include `python3 tools/agent_tools/check_convention_compliance.py` in the selected workflow closeout gates instead of restating every mechanical convention inside this prompt.
1. If the user explicitly asks for coding, implementation, or patch work to be delegated to subagents, treat that as explicit subagent implementation routing. Add `$subagent-bootstrap` and route through a write-capable handoff when ready; read-only survey/review roles support non-editing or setup phases.
1. Classify the request into one of these modes:
   - `repo-changing execution`: the user is asking to edit the repo, start the run, or produce a concrete kickoff command now
   - `routing-only/advisory`: the user wants workflow/skill/review guidance before repo edits
1. For repo-changing execution where the implementation owner needs routing, run `agent-canon local-llm route-implementation-surface --request-file <request.txt> --format text` before selecting edit paths. Use `PRIMARY_SURFACE`, `PRIMARY_PATHS`, `FORBIDDEN_PATHS`, and `REQUIRED_PRE_EDIT_CHECKS` as the source packet seed, and pass `PRIMARY_PATHS` into write-capable `allowed_paths` plus `FORBIDDEN_PATHS` into `do_not_read`. If LocalLLM is unavailable, use deterministic fallback output only as a provisional source-packet seed or record `router_unavailable_blocker`; confirm edit-path selection with responsibility search and dependency scope before handoff. Fallback routing reaches `fallback_exit_status` through `canonical_rerun_pass`, `durable_blocker_or_issue`, or `explicit_approval_evidence`.
1. Before reading broad prose, scanning raw logs, or spawning a subagent, check whether a canonical tool already owns the needed judgment. If yes, call the tool before prose review, trust its structured pass/finding output for the covered property, and read only the exact file slice needed to repair a finding.
1. Before continuing from any investigation or review, record which next step it changes: routing, edit location, validation, issue record, owner-held deferral, or out-of-scope note. If it leaves that choice unchanged, keep it as brief evidence in the current record and return to the current implementation, validation, or issue work.
1. Before scheduling expensive commands, create or cite a task-linked approval note with request clause, command type, lightweight evidence already used, expected runtime, resource target, stop condition, artifact path, and owner. Expensive command types include full CI, long test suites, benchmarks, experiments, GPU / CPU numerical runs, solver sweeps, and randomized large cases.
1. Before edit-path selection, parent-direct implementation, or write-capable subagent handoff, scale investigation to task risk. Broad surfaces, uncertain paths, and multi-agent handoffs need the `Pre-Edit Repository Investigation Packet` from `agents/COMMUNICATION_PROTOCOL.md`. Explicit-path, one-file, single-abstraction, Routine docs, Focused code, typo/link/format-only work needs the `Parent-Direct Context Note` from that document, including owner, path, request clause, reuse basis, design/OOP boundary, validation route, `llm_visible_context`, `local_tool_context`, and `durable_memory_refs`. Treat raw search hits, nearest editable files, or chat context alone as insufficient.
1. Choose exactly one primary workflow family from `agents/TASK_WORKFLOWS.md`. If a task id is known, treat the task-catalog mapping as the ground truth family.
1. For repo-changing tasks, choose the implementation route by design/OOP boundary and ownership clarity, not by apparent size alone. Parent-direct work is appropriate when the responsibility boundary, owner path, reuse plan, and validation route are clear and the work stays inside one replaceable responsibility unit. Use a multi-agent write-capable wave only when the user asks for it, or when independent replaceable targets can run in parallel without expanding scope or weakening design responsibility. Repo-wide scope, multiple surfaces, long document sets, or shared runtime surfaces do not by themselves authorize a multi-agent wave. If runtime authorization or tool gates block a requested write-capable handoff, record the blocker and `fallback_exit_status` instead of expanding read-only analysis.
1. Even when multi-agent routing is selected, split only at a replaceable unit boundary. A valid slice can be swapped for another implementation, proof, document responsibility, validation oracle, or review decision. Boundaries where no mathematical substitution can occur, notation-only seams, reading aids, fixed context, and continuous derivations that share one oracle stay in the same packet and owner scope.
1. Resolve subagent concurrency as a hierarchy:
   - runtime hard ceiling: `.codex/config.toml` `[agents].max_threads`
   - runtime nesting ceiling: `.codex/config.toml` `[agents].max_depth`, currently `2` for one bounded child-subagent layer
   - workflow active budget ceiling: `agents/task_catalog.yaml` `workflow_families[].spawn_budget.active_subagents`
   - stage wave plan: owner-owned bounded waves within the active budget; parent may delegate a stage owner to spawn child subagents when the handoff packet carries owner, input packet, expected output, dependency-expanded handoff scope, validation route, and review gate
   - independent workstreams become stage-owner vertical dynamic wave chains
   - write-capable budget: `workflow_families[].spawn_budget.max_write_subagents`, which limits only writer agents with disjoint write scopes
   - Intake Responsibility Wave is the responsibility intake wave; later roles are dynamic expansion waves triggered by evidence and stage gates
   - generated `team_manifest.yaml` must preserve `run.spawn_budget.active_subagents`, `run.spawn_budget.max_write_subagents`, `run.spawn_budget.runtime_max_threads`, `run.spawn_budget.runtime_max_depth`, `run.delegated_spawn_policy`, and `run.write_scope_policy.max_write_subagents`
1. Build the public skill set in this order:
   - when prompt-derived routing is needed, run `python3 tools/agent_tools/route.py --prompt "<user request>" --format json`; use `ACTIVE_SKILLS` for the current stage and carry `DEFERRED_SKILLS` as dynamic wave triggers instead of listing every possible skill up front
   - when `task_start.py` or `bootstrap_agent_run.py` is used, preserve its prompt-derived `SUGGESTED_SKILLS`, `ACTIVE_SKILLS`, `DEFERRED_SKILLS`, and `run.repo_tool_routing_policy`; use `REPO_DYNAMIC_SKILL_ROUTING_CANDIDATES` as later wave triggers and regenerate the selected skill command packet before each new handoff
   - lead with `$agent-orchestration` and preserve every user-provided `$skill-name`
   - add `$codex-task-workflow` when repo-changing execution starts
   - add `$subagent-bootstrap` only when an explicit handoff/wave is ready or the task shape requires subagent bootstrap evidence
   - add the task-shape skill set required by the current stage and contract:
     - research-backed implementation, benchmark, or external-research change -> `$research-workflow`
     - nontrivial or substantive document creation/addition/revision where section order, reader path, claim support, source map, canonical route, or document responsibility changes -> `$prose-reasoning-graph` as the common structure graph/DSL gate and `$structure-planning` as the structure contract gate; for typo/link/format-only edits, use `$md-style-check` and record `structure_contract=skipped` with the reason.
     - README, workflow, guide, migration, or other general explanatory reader-facing docs -> `$long-form-writing` as the DSL-to-prose projection adapter; select by document responsibility and reader contract, with length as a secondary signal.
     - submission paper or thesis-chapter draft -> `$paper-writing`
     - broader academic or scholarly-note writing outside paper-draft ownership -> `$academic-writing`
     - PR body, PR evidence comment, status update, decision brief, presentation narrative, PPT storyboard, or reader-facing report from tool, JSON/JSONL, hook, eval, checker, experiment, review, or audit evidence -> `$report-writing`; report output defaults to Markdown unless the user explicitly asks for HTML, browser view, dashboard, web page, or external browser publication; if PPT/deck is in scope, include a visual asset plan and slide-production workflow; if raw machine results are written or copied, also add `$result-artifact-writeout`
     - explicit HTML output, HTML report, browser-readable page, dashboard, local preview server, or external browser publication -> `$html-output`
     - explicit HTML experiment or Eval report -> `$html-experiment-report` plus `$html-output`
     - nontrivial report, experiment plan/report, Eval output, decision brief, presentation/PPT deck, HTML view, document, paper, or refactor structure; primary figure/table/ponchi-e/slide/section/slice choice; source map; source-to-slide map; or invalid interpretation boundary -> `$structure-planning`
     - tool/checker/hook/static-analysis runs to discover problems, create finding packets, compare before/after impact, or feed implementation/refactor planning -> `$tool-finding-report`; if raw results are written, also add `$result-artifact-writeout`; if the output is reader-facing narrative, also add `$report-writing`; if that narrative has a nontrivial finding packet, priority policy, metric/count contract, or source map, also add `$structure-planning`
     - README, workflow, guide, migration, or specification docs keep their domain projection adapter; add `$report-writing` as an overlay when the document includes evidence-backed status, evaluation, audit, review, decision, or recommendation sections
     - one-file or single-abstraction fixes, Routine docs, Focused code, typo/link/format-only edits, or explicit small change requests -> `$small-change-routing`; keep `selected_runtime_skill_read` and `small_change_skill_read` evidence before patching, and keep contract-complete implementation as the completion basis
     - large refactor -> `$refactor-loop`
     - directory layout, directory README responsibility, root view, path mapping, responsibility-scope map, or source-tree ownership refactor -> `$structure-refactor` plus `$refactor-loop`
     - expected AgentCanon repo structure, root view, `vendor/agent-canon/`, `.gitmodules`, or canonical path drift before an ordinary task -> `$structure-refactor` pre-task repair route; add `$agent-canon-update` for AgentCanon-owned root-view or submodule drift
     - environment / CI / Docker / dependency work -> `$environment-maintenance`
     - repo-wide workflow/tooling rearchitecture -> `$comprehensive-development`
     - iterative tuning or backlog-driven empirical improvement -> `$adaptive-improvement-loop`
     - optimizer, solver, preconditioner, gradient, Jacobian, Hessian, KKT, convergence, tolerance, numerical benchmark, or numerical-test diagnosis -> `$computational-optimization`
     - code-improvement hypothesis, cause analysis, hypothesis validation, fix-surface selection, multi-candidate comparison, change-impact packet creation, or repair-planning/subagent handoff context -> `$dependency-analysis` plus `agents/workflows/hypothesis-validation-workflow.md` as an overlay when a cause hypothesis is involved
     - Markdown file edits, docs lint/link/heading repair, Mermaid/math drift, formatter adjacent checks, `agent-canon docs`, docs-check failures, or Markdown style drift -> `$md-style-check`; pair substantive document edits with `$prose-reasoning-graph` and `$structure-planning`.
     - accumulated skill/tool/workflow/hook/eval log analysis, routing misses, selection gaps, or weak-skill diagnosis -> `$agent-log-analysis`
     - AgentCanon source update, `vendor/agent-canon` submodule latest/pin update, root runtime view repair, parent AgentCanon update TODOs, or `make agent-canon-ensure-latest` / `tools/update_agent_canon.sh` routing -> `$agent-canon-update`; add `$agent-update-branch` only when a parent-repo `canon-pin` branch lane is needed
     - user/reviewer feedback about agent behavior, repeated routing misses, recurrence prevention, task retrospectives, or agent-side memory updates -> `$agent-learning`
   - add only stage-relevant family skills; add neighboring catalog skills only when explicit task evidence requires them.
1. For repo-changing edits, read the full body of every selected runtime
   `SKILL.md`. The selected_runtime_skill_read contract applies to
   `Scoped Change Lite`, Routine docs, Focused code, typo/link/format-only, and
   parent-direct routes; use `$small-change-routing` to record small_change_skill_read evidence with skill
   names and paths ahead of patching.
1. Keep the advisory branch narrow. If the request is `routing-only/advisory`, defer repo-changing kickoff, run-bundle bootstrap, repo MCP tools, `check_mcp_inventory.py`, shell / GitHub checks, and repo-changing-only skills until explicit repo-changing intent is provided. In the interim, keep consultation, brainstorming, and explanation turns conversational until the user requests state inspection, file edits, validation, PR/issue processing, CI checks, or implementation execution.
1. Choose the starter command with explicit precedence:
   - if the request is `repo-changing execution`, or the user asks for the startup command / run bundle, prefer `python3 tools/agent_tools/bootstrap_agent_run.py --task "<task>" --task-id <T*> --owner codex --workspace-root "$PWD"`
   - use `python3 tools/agent_tools/task_start.py --task "<task>" --task-id <T*> --owner codex --workspace-root "$PWD"` only for routing-only starter guidance when no run bundle is being created yet
1. Emit a family-appropriate output set:
   - one chosen `workflow=<family>`
   - `skills=<...>` led by `$agent-orchestration`, preserved explicit skills, and only the needed additions
   - `review=<...>` plus the contract-required specialist / reviewer stack that matches that family
   - the starter command when the scenario asks for kickoff guidance
   - for execution tasks, the routing work-update declaration `workflow=<family>`, `skills=<...>`, `review=<...>`
1. For PR-producing repository tasks, carry that routing declaration into the PR body, run bundle, or linked comment with `skills=$agent-orchestration` as the leading skill and the result of `python3 tools/agent_tools/route.py --prompt "<user request>" --format json` when prompt-derived routing is relevant.
1. Mention Codex implementation routing only when implementation is in scope. Read `agents/canonical/CODEX_SUBAGENTS.md` before assigning agents.
1. For Routine docs or Focused code, parent-direct implementation is available when that route is selected before implementation and the risk class plus check matrix are selected. If the user requested subagent coding delegation and the write-capable route is blocked, record `WRITE_SUBAGENT_AUTHORIZATION=required` or the gate-specific blocker and reroute through `fallback_exit_status`; parent-direct continues only with `explicit_approval_evidence` or a revised workflow route whose completion gates match the original request. For subagent implementation, talk about `spark_worker` only after bootstrap or task-start output exposes `IMPLEMENTATION_CODEX_AGENTS`. Prefer `spark_worker` for approved slices derived from the Abstract Design Frame and design trace that are one file or one abstraction unit, public interface unchanged, no dependency change, no specification interpretation, and locally testable; use `worker` when design interpretation, broad architecture, scope judgment, or conflict resolution is required.
1. Use `explorer` or broad read-only review when tool-verified properties need additional abstraction for routing. Subagents receive structured tool artifacts and owned finding paths; if the tool output is missing an abstraction needed for routing, extend or repair the tool contract instead of replacing it with bulk prose reading.
1. For explicit subagent coding requests, first build the pre-handoff investigation packet from surface route seed, responsibility search, reuse survey, stale-surface scan, dependency expansion, validation route, and tool-rejection preflight. Then use the dependency-expanded handoff scope to schedule or launch `spark_worker` / `worker` before adding more read-only waves. If runtime authorization or tool gates block the write-capable spawn, record `WRITE_SUBAGENT_AUTHORIZATION=required` or the gate-specific blocker in the run bundle instead of replacing implementation with more read-only analysis.
1. Route detailed design, review, and final judgment through parent/direct or specialist flows; keep `spark_worker` out of those stages.
