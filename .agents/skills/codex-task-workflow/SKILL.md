---
name: codex-task-workflow
description: Use when Codex needs a context-independent execution path for a repository task, from intake and workflow selection through artifact placement, implementation, validation, and closeout.
---

<!--
@dependency-start
responsibility Documents Codex Task Workflow for this repository.
upstream design ../../../agents/canonical/CODEX_WORKFLOW.md defines the executable Codex workflow
upstream design ../../../documents/dependency-manifest-design.md defines dependency manifest requirements
upstream design ../../../agents/skills/codex-task-workflow.md documents the human-facing skill
upstream design ../../../agents/skills/tool-finding-report.md defines tool finding packets and prompt feedback decisions
@dependency-end
-->

# Codex Task Workflow

1. Read `agents/canonical/CODEX_WORKFLOW.md`.
1. Route skill selection through `$agent-orchestration` first; this skill executes the selected Codex task flow after routing is fixed.
1. Run `make agent-canon-ensure-latest` before planning or implementation when the AgentCanon update surface is repairable. In submodule repos, unrelated parent dirty state does not block this step. If the update surface itself is unsafe to refresh, route it through `agents/workflows/agent-canon-pr-workflow.md` or `agents/workflows/derived-agent-canon-diff-workflow.md`, merge the AgentCanon PR or proposal first, then rerun `make agent-canon-ensure-latest` and `bash tools/sync_agent_canon.sh link-root` in the template / derived repo.
1. Ordinary consultation, brainstorming, routing-only advice, and explanation-only turns are not repository tasks. For those, do not run `check_mcp_inventory.py`, repo MCP tools, shell commands, or GitHub checks; answer conversationally until the user asks to inspect repo state, edit files, run validation, process PRs/issues, check CI, or execute implementation work.
1. For repository tasks, decide whether MCP evidence is needed by the workflow or whether the task edits `.codex/config.toml`, `mcp/`, repo MCP tools, or MCP-dependent goal-loop gates. Run `agent-canon mcp-inventory --root . --require repo_mcp_server --session-cache` only for those cases, and use `python3 tools/agent_tools/check_mcp_inventory.py --require repo_mcp_server --report-dir <run>` only when run-bundle monitoring needs direct evidence. If Rust CLI or local Cargo cannot read AgentCanon lockfiles, record `mcp_preflight_unavailable=<reason>` and continue with Python/shell validation unless MCP runtime behavior is in scope.
1. Sweep `documents/`, `notes/`, `references/`, and local implementation directories before planning or implementation.
1. Classify the task with `agents/TASK_WORKFLOWS.md` before touching files.
1. In the first work update, declare `workflow=<family>`, `skills=<...>`, `review=<...>` with `$agent-orchestration` first in the skill list.
1. When skills are explicitly named in the task or handoff, use `$skill-name` notation and preserve it in `skills=<...>`.
1. During requirements, resolve avoidable ambiguity from notes, guardrails, documents, prior logs, and local code or tests before asking the user; record the sweep and evidence in `user_request_contract.md`.
1. Keep `unknown_or_open_question` out of active must-do, must-not-do, and completion-evidence clauses; move remaining unknowns to deferred or escalation entries after the sweep.
1. For Shared canon, Large delivery, high-risk, or multi-step repo-editing tasks, bootstrap subagents before implementation with `python3 tools/agent_tools/bootstrap_agent_run.py ... --enable scheduler --enable schedule_reviewer`, and keep the plan reviewer, detailed design reviewer, and document flow reviewer separate. Routine docs and Focused code may run parent-direct.
1. Use `agents/canonical/ARTIFACT_PLACEMENT.md` before creating task-facing documents.
1. Before detailed design narrows to edited paths, write or cite an abstract design frame: responsibility model, concept graph or layer model, non-goals, future extension layers, evaluation axes, and canonical-surface relationships. Implementation scope, file list, and validation must be derived from that frame rather than from the nearest editable path or current finding alone.
1. Before implementation path selection, run or cite `agent-canon local-llm route-implementation-surface --request-file <request-or-design-question.txt> --format text` unless the approved design packet already fixes the owner, canonical paths, forbidden paths, and required checks. Use that compact route instead of rereading broad implementation files to decide where code, tool, skill, workflow, document, or runtime-instruction changes belong.
1. Load only the minimal extra skills the task needs; nontrivial document creation or revision adds `prose-reasoning-graph` as the common graph/DSL gate, then file/document responsibility selects the DSL-to-prose adapter: general explanatory README/workflow/guide/migration/spec docs add `long-form-writing`, submission papers or thesis-chapter drafts add `paper-writing`, broader academic or scholarly-note writing adds `academic-writing`, and the required notation/logic/citation reviewers follow that adapter choice.
1. If the task needs explicit handoff or specialist roles, bootstrap `reports/agents/<run-id>/` first.
1. Update canonical docs before runtime entrypoints when both are affected.
1. Before implementation, read the approved `design_brief.md` `Abstract Design Frame`, `Implementation Source Packet`, and `Design-To-Implementation Trace`; confirm each implementation slice is derived from the abstract responsibility model before citing the design artifact path, design section, test-plan item, and user-request clause IDs.
1. Before implementation, read the approved `Dependency Manifest Plan`; load upstream dependency targets before editing and downstream targets after editing.
1. For new or edited human-authored text files, use only the `@dependency-start` / `@dependency-end` manifest format, not legacy `Dependency Files:` blocks.
1. If the design trace is missing or conflicts with repo docs or code, return to detailed design review instead of editing from chat context.
1. Before parent-direct edits or write-capable subagent edits, run or cite `python3 tools/agent_tools/tool_rejection_preflight.py --root . <planned-edit-paths>` and put predicted OOP, helper, dependency, hook runtime, skill mirror, tool catalog, protocol, and log-surface gates plus repair commands into the work log or handoff.
1. When implementation is driven by tool/checker/hook/reviewer/subagent findings, use `$tool-finding-report` first and pass the finding packet path, structured findings, impact, and prompt feedback decision into the parent or write-capable subagent handoff.
1. If `$tool-finding-report` classifies feedback as `handoff_prompt_gap` or `shared_skill_or_workflow_gap`, repair the handoff prompt, skill, workflow, or task catalog prompt before launching the next write-capable subagent.
1. For low-risk implementation slices derived from the Abstract Design Frame and design trace, use `spark_worker` first and `worker` as alternate route; keep requirements, design, review, and scope judgment off Spark.
1. Treat chunks, slices, checkpoints, and subpasses as internal progress only; continue until all planned work units, active clauses, final review, validation, closeout gate, commit, and push are complete.
1. Validate dependency manifests with `python3 tools/agent_tools/check_dependency_headers.py --changed`, `bash tools/agent_tools/scan_dependency_headers.sh --changed --fail-missing`, and `bash tools/agent_tools/check_dependency_header_format.sh --changed --require-header` before closeout.
1. If dependency edges changed, run `bash tools/agent_tools/check_dependency_graph.sh --print-edges` or record the migration baseline and evidence that the current diff introduced no new graph error.
1. Run `python3 tools/agent_tools/check_convention_compliance.py` before closeout for Shared canon, Large delivery, high-risk, or workflow/tooling changes so workflow prohibitions, convention tool gates, and skill-routing hooks are verified by the tool instead of repeated in prompt prose.
1. Validate with `make ci-quick` first and escalate to broader checks only when needed.
