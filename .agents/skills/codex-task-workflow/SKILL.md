---
name: codex-task-workflow
description: Use when Codex needs a context-independent execution path for a repository task, from intake and workflow selection through artifact placement, implementation, validation, and closeout.
---

<!--
@dependency-start
contract skill
responsibility Documents Codex Task Workflow for this repository.
upstream design ../../../agents/canonical/CODEX_WORKFLOW.md defines the executable Codex workflow
upstream design ../../../agents/COMMUNICATION_PROTOCOL.md defines pre-edit investigation and context capsule handoff packets
upstream design ../../../documents/dependency-manifest-design.md defines dependency manifest requirements
upstream design ../../../documents/BRANCH_SCOPE.md defines Git commit correctness and push evidence
upstream design ../../../agents/skills/codex-task-workflow.md documents the human-facing skill
upstream design ../../../agents/skills/tool-finding-report.md defines tool finding packets and prompt feedback decisions
@dependency-end
-->

# Codex Task Workflow

## Reader Map

- Purpose: runtime skill for executing repository tasks through the canonical
  Codex workflow from intake to closeout.
- Use When: repo-changing work needs source packets, artifact placement,
  implementation routing, validation, review, and completion evidence.
- Tool Commands: run this skill's command packet, then read the canonical
  `agents/skills/codex-task-workflow.md` route and task-matching checks.
- Boundary: this workflow coordinates execution; selected task-shape skills own
  domain-specific rules.

## Tool Commands

<!-- skill-tool-commands:start -->
Use the command packet before applying this skill's workflow:

```bash
python3 tools/agent_tools/skill_tool_commands.py show --skill codex-task-workflow --format text
```

Execute the required and task-matching conditional commands that the packet prints.
<!-- skill-tool-commands:end -->


1. Read `agents/canonical/CODEX_WORKFLOW.md`.
1. Route skill selection through `$agent-orchestration` first; this skill executes the selected Codex task flow after routing is selected.
1. Run `make agent-canon-ensure-latest` before planning or implementation when the AgentCanon update surface is repairable. In submodule repos, the blocking scope is the AgentCanon update surface. If the update surface itself is unsafe to refresh, route it through `agents/workflows/agent-canon-pr-workflow.md` or `agents/workflows/derived-agent-canon-diff-workflow.md`, merge the AgentCanon PR or proposal first, then rerun `make agent-canon-ensure-latest` and `bash tools/sync_agent_canon.sh link-root` in the template / derived repo.
1. When AgentCanon source, submodule pin, `.gitmodules`, AgentCanon-owned root runtime view, root-copy surface, or parent root sync changes, record `agentcanon_structure_followup=required`. Use `bash tools/sync_agent_canon.sh link-root` and `bash tools/sync_agent_canon.sh check` in the template / derived parent root, then record `agentcanon_structure_followup=pass` only after both commands pass.
1. Ordinary consultation, brainstorming, routing-only advice, and explanation-only turns are conversational turns. For those, keep `check_mcp_inventory.py`, repo MCP tools, shell commands, and GitHub checks in hold until the user requests state inspection, file edits, validation, PR/issue processing, CI checks, or implementation work, and continue with conversational responses until then.
1. For repository tasks, decide whether MCP evidence is needed by the workflow or whether the task edits `.codex/config.toml`, `mcp/`, repo MCP tools, or MCP-dependent goal-loop gates. Run `agent-canon mcp-inventory --root . --require repo_mcp_server --session-cache` for those cases, and use `python3 tools/agent_tools/check_mcp_inventory.py --require repo_mcp_server --report-dir <run>` when run-bundle monitoring needs direct evidence. If Rust CLI or local Cargo has no access to AgentCanon lockfiles, record `mcp_preflight_unavailable=<reason>` and continue with Python/shell validation; MCP runtime behavior in scope keeps MCP evidence active.
1. Before sweeping `documents/`, `notes/`, `references/`, or local implementation directories, create or cite the `Structure Intake Packet` from `agents/COMMUNICATION_PROTOCOL.md`. Use its structure-reading artifacts as the entrypoint for choosing owner, document, and implementation surfaces; promote exact prose excerpts only after the packet shows they affect the next decision.
1. Preserve the user's requested scope before deriving work packets. Record `requested_scope` from the request clauses, then derive `work_scope` from owner boundaries, dependency evidence, and validation route. A bounded `work_scope` is allowed only as an implementation phase with explicit `covered_surfaces`, `deferred_surfaces`, and `omitted_surfaces` evidence; it is not completion evidence for a broader request.
1. Keep sweeps and cause investigations tied to the next concrete work. Each result updates one of: implementation route, reuse decision, stale-surface repair, dependency scope, validation route, durable issue, or explicit deferred owner. Evidence that leaves those fields unchanged stays as a short citation in the packet, then control returns to the current step.
1. Keep validation centered on static/read evidence. Use static analysis,
   dependency checks, docs checks, route checks, source/contract reading, and
   changed-file targeted tests as the primary validation evidence. Treat
   operation checks, smoke runs, full CI, long test suites, benchmarks,
   experiments, GPU / CPU numerical runs, solver sweeps, and randomized large
   cases as supplemental evidence only when changed runtime behavior,
   integration risk, or unresolved static findings require them. Record what
   the static/read evidence left unresolved before scheduling broader
   execution.
1. Before touching files, record a provisional workflow route from `agents/TASK_WORKFLOWS.md` and keep it revisable until owner boundary, replaceable unit, validation route, and public behavior / schema impact are evidenced.
1. In the first work update, declare `workflow=<provisional-or-final-family>`, `skills=<...>`, `review=<...>` with `$agent-orchestration` first in the skill list, and present apparent breadth only as provisional routing context.
1. When skills are explicitly named in the task or handoff, use `$skill-name` notation and preserve it in `skills=<...>`.
1. Treat `run.repo_tool_routing_policy` from `task_start.py` or `bootstrap_agent_run.py` as the selected repo-owned tool route. Carry `tool_route`, `tool_commands`, and `tool_evidence` into subagent handoff packets, and run each selected skill packet in the manifest order before replacing it with prose review.
1. For repo-changing edits, existing tool execution and owner-bounded patching
   proceed from tool-owned evidence. Runtime `SKILL.md` reading is optional
   follow-up context after the existing tool or selected command packet runs for
   the covered property. Read only the owner surface needed to interpret or
   repair the tool result. Route owner-bounded edits through
   `$owner-bounded-routing` and record owner, existing-tool route, and
   targeted-validation evidence.
1. For research-backed implementation, benchmark, external-research change,
   prior-art adoption, official-docs method claims, or literature-derived design
   decisions, the emitted `skills=...` / run-bundle skill call sequence calls
   `$literature-survey` before `$research-workflow`, before design, and before
   implementation. Carry the durable source packet into the
   `Implementation Source Packet` with source class, limitation, contrary or
   narrowing evidence, and adoption/exclusion decisions. Implementation,
   benchmark, report, and owner-bounded follow-up branches may not close a
   literature-backed claim from transient browser context or post-hoc citation
   cleanup.
1. ユーザー向けの作業更新、最終報告、レビュー要約、handoff guidance、reader-facing docs は日本語で書く。内部の field name、enum value、role key、helper 風の語は、command、path、table、正確な evidence reference に閉じる。専門語が必要な場合は、既存の repository term または外部標準 term を使い、自然文で説明する。
1. During requirements, resolve avoidable ambiguity from notes, guardrails, documents, prior logs, and local code or tests before asking the user; record the sweep and evidence in `user_request_contract.md`.
1. Keep `unknown_or_open_question` out of active must-do, must-not-do, and completion-evidence clauses; move remaining unknowns to deferred or escalation entries after the sweep.
1. For repo-changing implementation / patch / doc-edit work, bootstrap or schedule write-capable `spark_worker` / `worker` handoff before implementation and keep the plan reviewer, detailed design reviewer, and document flow reviewer separate. Routine docs and Focused code still use targeted validation, but parent repository edits require `PARENT_DIRECT_WRITE_EXCEPTION_REQUIRED=yes` and `PARENT_DIRECT_WRITE_EXCEPTION=<explicit_user_approval|runtime_blocker>`.
1. If the user explicitly asks for subagent coding/implementation/patch/editing, route completion through write-capable `spark_worker`/`worker` (or equivalent write-capable subagent wave) after the pre-handoff investigation packet derives dependency-expanded handoff scope, validation route, and `tool_rejection_preflight` evidence from route seed, responsibility search, reuse survey, and stale-surface scan.
1. Use `agents/canonical/ARTIFACT_PLACEMENT.md` before creating task-facing documents.
1. Before detailed design selects implementation paths, write or cite an abstract design frame: responsibility model, concept graph or layer model, non-goals, future extension layers, evaluation axes, and canonical-surface relationships. Implementation scope, file list, and validation must be derived from that frame rather than from the nearest editable path or current finding alone.
1. Before implementation path selection, run or cite `agent-canon local-llm route-implementation-surface --request-file <request-or-design-question.txt> --format text` unless the approved design packet already fixes the owner, canonical paths, forbidden paths, and required checks. Use that structured route instead of rereading broad implementation files to decide where code, tool, skill, workflow, document, or runtime-instruction changes belong. If LocalLLM is unavailable, use deterministic fallback `PRIMARY_PATHS` / `FORBIDDEN_PATHS` only as a provisional source-packet seed or record `router_unavailable_blocker`; confirm owner and edit scope with responsibility search plus dependency scope before patching. Fallback routing reaches `fallback_exit_status` through `canonical_rerun_pass`, `durable_blocker_or_issue`, or `explicit_approval_evidence`.
1. Before edits, create or cite the protocol-owned `Pre-Edit Repository Investigation Packet` from `agents/COMMUNICATION_PROTOCOL.md`. If this packet is missing or shallow, return to investigation before patching.
1. Close the `Pre-Edit Repository Investigation Packet` by naming the next concrete step and one owner. Continue with that step before opening another line of exploration.
1. Close the validation route by stating the static/read evidence used as the
   primary confirmation, whether broader execution is supplemental and
   approved, and the owner. Use static-only validation for policy, docs,
   metadata, contract-only wrappers, and checker-owned properties.
1. If a validation test or check fails, keep implementation intent, intended
   behavior, tests, slice contents, oracle strength, and validation scope stable
   until the packet records `failing_contract`, `observation_level`,
   `cause_classification`, `intent_preservation`, and `evidence`. Use
   `intent_preservation` for the same-intent repair or escalation route.
   Preserve approved intent for implementation bugs; repair test/design
   evidence for oracle or spec mismatches; route fixture, environment, or stale
   generated artifact failures to their owner; record unrelated failures as
   residual; escalate approved-design/user-request conflicts before changing
   intent.
1. Before commit or push, satisfy the `documents/BRANCH_SCOPE.md` commit correctness contract and scope-split contract: treat the commit as the runnable Git unit and the PR as the review unit; include every validation-read source/config/schema/fixture/doc/tool entrypoint in the tracked tree; when a diff spans multiple problems, canonical owners, behavior or contract deltas, or validation routes, write a scope table and split independently landable slices into separate PRs or commits before merge; for code changes record file-level code dependency plus function/public-entrypoint call-site evidence when language tools support it; and record branch, commit SHA, submodule SHA, validation commands, validation paths, and any remaining dirty or untracked path classification.
1. Load the extra skills required by the current stage and contract; carry unrelated skills as deferred route signals. Nontrivial document creation or revision adds `prose-reasoning-graph` as the common graph/DSL gate and `$structure-planning` as the structure contract gate, then file/document responsibility selects the DSL-to-prose adapter: general explanatory README/workflow/guide/migration/spec docs add `long-form-writing`, submission papers or thesis-chapter drafts add `paper-writing`, broader academic or scholarly-note writing adds `academic-writing`, and the required notation/logic/citation reviewers follow that adapter choice. For typo/link/format-only edits, pair `$md-style-check` with `structure_contract=skipped` and the reason.
1. When the evidence shows a bounded owner, replaceable unit, targeted validation route, and no public behavior / schema expansion, or when the work is Routine docs, Focused code, or typo/link/format-only, add `$owner-bounded-routing` before patching and keep targeted validation as the closeout route. File count is only auxiliary context.
1. If the task needs explicit handoff or specialist roles, bootstrap `reports/agents/<run-id>/` first.
1. Update canonical docs before runtime entrypoints when both are affected.
1. Before implementation, close the Design Integrity Gate: the `Abstract Design Frame` or parent-direct design-boundary note must name the responsibility model, replaceable unit, non-goals, and validation route before file-level work starts. Missing API shape, responsibility boundary, path layout, naming, algorithm, test oracle, dependency direction, runtime contract, or config-surface decisions are `design_issue_blocker` findings, not implementation latitude.
1. Before implementation, read the approved `design_brief.md` `Abstract Design Frame`, `Implementation Source Packet`, `Design Side-Effect Map`, and `Design-To-Implementation Trace`; confirm each implementation slice and downstream side effect is derived from the abstract responsibility model before citing the design artifact path, design section, test-plan item, and user-request clause IDs.
1. If implementation exposes a design issue, record `design_issue_blocker=<issue>` plus evidence and return to detailed design / design review. API shape, responsibility boundary, path layout, naming, algorithm, theorem target, test oracle, dependency direction, runtime contract, and config-surface gaps resolve through design review, with local fallback, wrappers, helpers, branches, compatibility routes, test relaxation, and docs overwrite treated as out-of-scope routes.
1. Close each implementation slice as a contract-complete implementation. Link the request clause, acceptance contract, `Implementation Source Packet`, and validation route; if the work would shrink the requested behavior into an implementation shortcut, record `design_issue_blocker=<issue>` plus evidence and return to design review.
1. Treat apparent breadth, `Owner-Bounded Change`, MVP, and thin slice labels as provisional routing, wave, and validation-profile signals. Implementation behavior is derived from the request clauses, acceptance contract, implementation source packet, design trace, dependency-expanded scope, validation route, and review gate. Revise the route when those sources show a different owner boundary or impact surface.
1. Only typo, formatting, import, and bounded mechanical follow-through that is uniquely determined by the approved design, local precedent, and existing responsibility boundary may be fixed in the same implementation pass. Anything requiring judgment is a design issue.
1. For implementation slices that touch classes, dataclasses, `Protocol`, inheritance, public API, type boundaries, or dependency direction, route `$oop-readability-check` into validation and carry SOLID principle signal counts, OOP dimension, finding kind, and the `tools/oop/shared/readability_core.py` mapping into the design artifact.
1. For SOLID-sensitive Python slices, validate evidence coverage with `python3 tools/agent_tools/check_solid_evidence.py --changed --evidence <oop-readability-report>` so the OOP readability report covers the changed path through `scanned_paths`.
1. Before implementation, read the approved `Dependency Manifest Plan`; load upstream dependency targets before editing and downstream targets after editing.
1. For new or edited human-authored text files, use the current `@dependency-start` / `@dependency-end` manifest format.
1. If the design trace is missing or conflicts with repo docs or code, return to detailed design review instead of editing from chat context.
1. Before parent-direct edits or write-capable subagent edits, run or cite `python3 tools/agent_tools/tool_rejection_preflight.py --root . <planned-edit-paths>` and put predicted OOP, helper, dependency, responsibility_scope, hook runtime, skill mirror, tool catalog, protocol, and log-surface gates plus repair commands into the work log or handoff. Record the owner scope and protecting tools before selecting the implementation directory.
1. For fresh subagent launches, include the protocol-owned `Fresh Subagent Context Capsule` from `agents/COMMUNICATION_PROTOCOL.md` instead of chat history, full transcripts, raw logs, full dashboards, or repo-root scope.
1. If runtime/tool gates block write-capable spawn, record `WRITE_SUBAGENT_AUTHORIZATION=required` or the specific gate blocker and route the slice through `fallback_exit_status`; continue by rerunning the canonical gate to `canonical_rerun_pass`, opening `durable_blocker_or_issue`, or attaching `explicit_approval_evidence` for a revised workflow route.
1. When implementation is driven by tool/checker/hook/reviewer/subagent findings, use `$tool-finding-report` first and pass the finding packet path, structured findings, impact, and prompt feedback decision into the parent or write-capable subagent handoff.
1. If `$tool-finding-report` classifies feedback as `handoff_prompt_gap` or `shared_skill_or_workflow_gap`, repair the handoff prompt, skill, workflow, or task catalog prompt before launching the next write-capable subagent.
1. For low-risk implementation slices derived from the Abstract Design Frame and design trace, use `spark_worker`; use `worker` for slices requiring design interpretation, conflict resolution, broader architecture judgment, or scope judgment.
1. Treat chunks, slices, checkpoints, and subpasses as internal progress only; continue until all planned work units, active clauses, final review, validation, closeout gate, commit, and push are complete.
1. Validate dependency manifests with `python3 tools/agent_tools/check_dependency_headers.py --changed`, `bash tools/agent_tools/scan_dependency_headers.sh --changed --fail-missing`, and `bash tools/agent_tools/check_dependency_header_format.sh --changed --require-header` before closeout.
1. If dependency edges changed, run `bash tools/agent_tools/check_dependency_graph.sh --print-edges` or record the migration baseline and evidence that the current diff introduced no new graph error.
1. Run `python3 tools/agent_tools/check_convention_compliance.py` before closeout for Shared canon, Large delivery, high-risk, or workflow/tooling changes so workflow readiness, convention tool gates, and skill-routing hooks are verified by the tool instead of repeated in prompt prose.
1. Validate with the static/read route first. Broader execution uses the
   task-linked approval note and records the static or reading signal that
   remained unresolved.
