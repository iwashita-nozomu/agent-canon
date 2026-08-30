# runtime-log-repair
<!--
@dependency-start
contract skill
responsibility Documents runtime-log-repair for this repository.
upstream design ../canonical/skills.md skill canon registry
upstream design agent-log-analysis.md structured dashboard analysis and finding route packets
upstream design agent-eval-accumulation.md accumulated eval repair loop
upstream design result-artifact-writeout.md durable raw and summary artifact writeout
upstream design issue-finding-report.md durable issue candidate writing
upstream implementation ../../eval/producers/generate_agent_runtime_dashboard.py owns dashboard API fields
downstream implementation ../../.codex/personal/skills/runtime-log-repair/SKILL.md exposes this workflow as a runtime skill
@dependency-end
-->

## Reader Map

- Purpose: turns structured AgentCanon runtime dashboard findings into an
  owner-routed Runtime Log Repair Packet and verifies the repair closeout.
- Use When: dashboard next actions, hook failure evidence, missing actual wave
  rows, workflow attribution gaps, missing consulted source URLs, or recurring
  runtime-log repair work need routed action rather than more analysis.
- Section path: Purpose and Use When define the trigger; Required Flow fixes the
  packet and closeout sequence; Boundaries keep raw analysis, durable issues,
  and owner-specific repairs with their existing skills.
- Boundary: this skill coordinates repair routing from dashboard evidence; it
  does not own the dashboard schema, raw log analysis, hook implementation,
  subagent mechanics, prompt/config review, durable issue writing, or reference
  extraction internals.

## Purpose

`agent-log-analysis` が作成した compact dashboard / API evidence から、次に
直すべき runtime-log 問題を owner surface へ分配する skill です。観測値を
直接 patch に変換せず、Runtime Log Repair Packet に evidence cell、owner、
required follow-up skill、validation gate を固定してから修復へ進みます。

## Use When

- runtime dashboard の next actions を処理する
- hook entries `status=fail`、`AGENT_RUNTIME_DASHBOARD_HOOK_WORKFLOW_MISSING`、
  `AGENT_RUNTIME_DASHBOARD_WAVE_MISSING_ACTUAL`、または
  `AGENT_RUNTIME_DASHBOARD_REFERENCE_MISSING_URLS` を修復へ回す
- missing actual wave rows、workflow attribution gaps、consulted source URLs
  missing、reference missing URLs を owner-routed repair にする
- dashboard evidence が raw analysis ではなく実装・設定・記録の修復を要求している
- 頻発する runtime-log repair work を skill / tool / workflow owner に分解する

## Required Flow

1. Start from `agent-log-analysis` dashboard artifacts:
   `agent-log-analysis-api.json` and `agent-log-analysis-compact.md`. If these
   are missing or stale for the current request, run `$agent-log-analysis`
   first; do not read raw JSONL broadly as a substitute.
1. Classify each repair item by owner:
   `hook_failure`, `wave_execution`, `workflow_attribution`,
   `reference_capture`, `skill_selection`, `tool_selection`, `eval_gap`,
   `archive_hygiene`, or `prompt_or_config_drift`.
1. Write a Runtime Log Repair Packet before editing or spawning a repair wave:

```text
repair_class=<hook_failure|wave_execution|workflow_attribution|reference_capture|skill_selection|tool_selection|eval_gap|archive_hygiene|prompt_or_config_drift>
dashboard_evidence=<compact section or API field path>
owner_surface=<canonical skill/tool/workflow/hook/document path>
repair_route=<skill-or-role>
required_input=<dashboard artifact, eval output, or owner path>
non_goals=<raw log analysis, schema change, durable issue writing, or owner-specific internals excluded>
closeout_gate=<command or dashboard field that proves routed repair completion>
```

1. Route owner work without absorbing it into this skill:
   - skill/tool/workflow selection repair -> `$task-routing` plus affected owner
   - eval family repair -> `$agent-eval-accumulation`
   - raw/summary artifact placement -> `$result-artifact-writeout`
   - durable issue candidates -> `$issue-finding-report`
   - subagent wave mechanics -> `$subagent-bootstrap`
   - recurrence learning -> `$agent-learning`
1. For hook failure, workflow attribution, wave reconciliation, and reference
   capture repairs, cite the dashboard evidence cell and the owner path named by
   the dashboard summary before touching hook, monitoring, schedule, reference,
   or closeout tooling.
1. Verify closeout with the owner-selected gate and, when the repair changes
   dashboard-producing behavior or routing, rerun the focused route/eval/check
   that covers the changed owner. A full dashboard rerun is evidence only when
   the owner gate requires accumulated post-change measurement.
1. owner-selected gate が fail した場合は、runtime-log repair intent の変更、
   pass 目的の単純化、revert、intended behavior / test 削除、oracle weakening、
   validation downscope の前に `failing_contract`、`observation_level`、
   `cause_classification`、`intent_preservation`、`evidence` を Runtime Log
   Repair Packet へ追記します。dashboard/schema/tooling の implementation bug は
   owner intent を保って修復し、oracle / spec、fixture / environment / stale
   artifact、unrelated failure、approved-design / user-request conflict は owner
   route、residual、または escalation に分けます。

## Boundaries

Archive branch identity, legacy inventory, retention, and migration authority
belong to the `agent-canon-log` policy repository. This skill routes dashboard
evidence and does not duplicate those policy definitions.

- Raw log compaction and dashboard API schema belong to `$agent-log-analysis`
  and `generate_agent_runtime_dashboard.py`.
- Eval producer loops belong to `$agent-eval-accumulation`.
- Artifact placement and durable raw/summary writeout belong to
  `$result-artifact-writeout`.
- Durable issue creation belongs to `$issue-finding-report`.
- Subagent launch mechanics and wave lifecycle records belong to
  `$subagent-bootstrap`.
- Prompt/config review belongs to `$task-routing`, affected skill owners, and
  the prompt/config reviewer role.
- Hook implementation details, workflow monitoring internals, and reference extraction internals stay with their owner surfaces.

## Runtime Contract Clauses

The runtime discovery adapter delegates these required operating clauses to this canonical owner.

1. Read `agents/skills/runtime-log-repair.md`.
1. Start from `$agent-log-analysis` dashboard artifacts:
   `reports/agent-runtime-dashboard/agent-log-analysis-api.json` and
   `reports/agent-runtime-dashboard/agent-log-analysis-compact.md`. If they are
   missing or stale for the request, run `$agent-log-analysis` first.
1. Do not read raw JSONL broadly for normal repair routing; raw event drilldown
   stays with `$agent-log-analysis` tool development, schema debugging, or an
   API-named drilldown path.
1. Build a Runtime Log Repair Packet with `repair_class`,
   `dashboard_evidence`, `owner_surface`, `repair_route`, `required_input`,
   `non_goals`, and `closeout_gate` before editing or launching repair work.
1. Route repairs to owners: eval gaps to `$agent-eval-accumulation`, durable
   artifacts to `$result-artifact-writeout`, issue candidates to
   `$issue-finding-report`, wave mechanics to `$subagent-bootstrap`,
   prompt/config or selection repair to `$task-routing` plus the affected owner,
   and recurrence learning to `$agent-learning`.
1. Keep boundaries explicit: this skill does not own raw log analysis,
   dashboard schema, eval producer loops, artifact placement, durable issue
   writing, subagent launch mechanics, prompt/config review, hook
   implementation details, or reference extraction internals.
1. Verify closeout with the owner-selected gate. Rerun a full dashboard only
   when the owner gate needs accumulated post-change evidence.
1. If the owner-selected gate fails, add `failing_contract`,
   `observation_level`, `cause_classification`, `intent_preservation`, and
   `evidence` to the Runtime Log Repair Packet before changing repair
   intent, simplifying to pass, reverting, deleting intended behavior/tests,
   weakening an oracle, or downscoping validation. Preserve owner intent for
   implementation bugs and route oracle/spec, fixture/environment/stale
   artifact, unrelated, and approved-design/user-request conflicts to owner
   repair, residual, or escalation.
