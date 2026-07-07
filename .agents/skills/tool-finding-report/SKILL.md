---
name: tool-finding-report
description: Use when running tools, checkers, hooks, static analysis, or structural analyzers to find problems, preserve raw and structured full finding artifacts, mechanically rank every finding, and produce a complete finding report for implementation or refactor planning; before/after impact is optional when explicitly requested.
---
<!--
@dependency-start
contract skill
responsibility Documents Tool Finding Report runtime skill for this repository.
upstream design ../../../agents/skills/tool-finding-report.md documents the human-facing workflow
upstream design ../../../agents/skills/result-artifact-writeout.md defines raw result artifact policy
upstream design ../../../agents/skills/report-writing.md defines reader-facing report policy
upstream design ../../../agents/skills/refactor-loop.md consumes finding packets for repair slices
upstream implementation ../../../tools/agent_tools/check_design_doc_claims.py emits design evidence findings
@dependency-end
-->

# Tool Finding Report

## Tool Commands

<!-- skill-tool-commands:start -->
Use the command packet before applying this skill's workflow:

```bash
python3 tools/agent_tools/skill_tool_commands.py show --skill tool-finding-report --format text
```

Execute the required and task-matching conditional commands that the packet prints.
<!-- skill-tool-commands:end -->


1. Read `agents/skills/tool-finding-report.md`.
1. Default the target scope to the full repository before running tools. Fix exclude rules, dependency roots, and output directory. Use targeted, changed-only, or selected-path scope only when the user explicitly asks for it, the tool cannot run repo-wide, or it is an additional diagnostic beside the full-repository run; record `scope_exception=<reason>`, `requested_scope=<...>`, and `omitted_surfaces=<...>` in the finding packet. Fix a baseline ref only when before/after impact is explicitly requested.
1. Preserve raw machine results first with `$result-artifact-writeout`; failed or partial runs are evidence, not noise.
1. When failed validation/check output feeds implementation, include the
   validation-failure-response packet fields (`failing_contract`,
   `observation_level`, `cause_classification`, `intent_preservation`, and
   `evidence`) in the finding packet.
1. Build structured full-repository artifacts from the raw results before interpreting them. Do not truncate to top-N findings inside this skill. For Python structural findings, use `python-structure-hash` -> `python-structure-hash-report`, and use `python-structure-hash-impact` only when before / after comparison is requested.
1. When the structured Python findings will feed implementation or refactor
   planning, preserve the full report and call
   `python-structure-hash-scope-plan` through `$dependency-analysis` after the
   dependency review directory exists. The scope-plan JSON, not a chat
   summary, is the mechanical source for `impact_blocks`, `scope_candidates`,
   `selected_scope`, and `repair_batches`.
1. Include the relevant checker family for the task: algorithm contract, module groups, OOP readability, dependency review, design-claim evidence, static analysis, hook logs, or workflow evals.
1. If any tool, hook, checker, guardrail, or migration wrapper emits a warning, immediately register it as a closeout obligation in run-local `reports/agents/<run-id>/workflow_monitoring.md` with `workflow_monitor.py --tool-warning "warning_id=<stable-id> source_tool=<tool> severity=<warning|fix-now|s0|s1> status=open message=<short-no-spaces> repair_command=<command-or-doc>"`. The reusable template for that file is `agents/templates/workflow_monitoring.md`. After repair, append the same `warning_id` with `status=resolved evidence=<path-or-command>`. Normal warnings reach `tool_warning_exit_status` through `resolved`, `deferred_with_issue issue=<issue-or-pr>` with durable owner, or `accepted_with_reason` with `explicit_approval_evidence` and a durable rationale artifact; fix-now / S0 / S1 warnings must be resolved. If the run observed no warnings, run `workflow_monitor.py --tool-warning-status none` before closeout.
1. Mechanically rank every finding. If the tool does not provide priority, derive a deterministic order from severity, public API or algorithm-contract impact, dependency fan-in/fan-out, duplicate/thin/single-caller signals, production vs test/experiment scope, and tool confidence. Record the ranking policy in the report.
1. Write a finding packet with scope, scope exceptions if any, commands, raw artifacts, structured artifacts, full counts, full finding table or structured finding artifact reference, mechanical priority order, optional impact, and a handoff boundary. The caller or higher-level workflow chooses the repair slice and decides what to do next.
1. Use `$report-writing` when the user needs a reader-facing narrative report; keep mechanical tool output and agent interpretation separated.
   - This is mandatory when the user asks for a report, summary, interpretation, explanation of findings, or a Markdown reader artifact.
   - Do not close with only a validation summary, command log, top-N excerpt, or raw JSON pointer. Produce a reader-facing finding report with the `$report-writing` required sections.
   - For nontrivial finding packets, also apply `$structure-planning` before drafting so the report has a source packet, reader guide, metric/count contract, priority policy, limitations, and next actions.
   - The report may reference the full structured artifact instead of embedding every row, but it must state that the full finding table is preserved there and must not truncate the underlying artifact.
1. If findings drive behavior-preserving implementation or refactor, pass the full finding packet and mechanical priority order to `$refactor-loop` instead of editing from a chat-only summary.
1. Classify each tool/reviewer/subagent feedback item as `implementation_bug`, `missing_test_or_design_evidence`, `handoff_prompt_gap`, `shared_skill_or_workflow_gap`, `tool_gap`, or `review_required`.
   Use `missing_design_claim_evidence` when `check_design_doc_claims.py` reports an implementation-backed design claim without code, dependency-header, parent-doc, or assumption-ledger support.
1. For `handoff_prompt_gap` or `shared_skill_or_workflow_gap`, repair the next subagent handoff or shared skill/workflow prompt before launching the next write-capable subagent, and record `workflow_monitor.py --runtime-feedback ... action=prompt_repair`.
