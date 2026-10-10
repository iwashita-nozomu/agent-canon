# runtime-log-repair
<!--
@dependency-start
contract skill
responsibility Documents runtime-log-repair for this repository.
upstream design ../canonical/skills.md skill canon registry
upstream design agent-log-analysis.md structured dashboard analysis and finding route packets
upstream design ../../documents/runtime/runtime-log-archive.md runtime delivery and archive maintenance ownership
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
- Section path: Purpose and Use When define the trigger; Required Flow connects
  selected findings to owner decisions and closeout; Boundaries keep raw analysis, durable issues,
  and owner-specific repairs with their existing skills.
- Boundary: this skill coordinates repair routing from dashboard evidence; it
  does not own the dashboard schema, raw log analysis, hook implementation,
  subagent mechanics, prompt/config review, durable issue writing, or reference
  extraction internals.

## Purpose

`agent-log-analysis` が選んだ compact dashboard / API evidence から、修復が
選択された項目を owner surface につなぐ skill です。観測だけでは patch や
repair wave を起動しません。修復を行う場合は既存の Runtime Log Repair Packet
で根拠、担当、入力、適用する closeout を伝えます。

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

Start with the evidence selected by `$agent-log-analysis`: one existing API JSON,
compact summary, or bounded snapshot-qualified excerpt is enough when it supports
the item. Preserve its scope, age, and gaps. Neither both formats, regeneration,
archive sync, nor clean state is a prerequisite for an otherwise supported
finding; do not expand raw JSONL broadly.

For a repair that is actually selected, identify its owner from the observed
failure and affected surface. Use the existing classes below only where they fit;
an item that crosses owners may need more than one responsibility, and an
uncertain cause stays uncertain. Before editing or launching a repair wave,
carry the evidence and selected operation in the existing Runtime Log Repair
Packet:

```text
repair_class=<hook_failure|wave_execution|workflow_attribution|reference_capture|skill_selection|tool_selection|eval_gap|archive_hygiene|prompt_or_config_drift>
dashboard_evidence=<compact section, API field, or snapshot-qualified excerpt and evidence gaps>
owner_surface=<canonical skill/tool/workflow/hook/document path>
repair_route=<skill-or-role>
required_input=<available summary/excerpt, eval output, or owner path>
non_goals=<raw log analysis, schema change, durable issue writing, or owner-specific internals excluded>
closeout_gate=<command or dashboard field that proves routed repair completion>
```

Route the operation to its existing owner: selection repairs use `$task-routing`
and the affected owner; eval repair uses `$agent-eval-accumulation`; delivery or
archive maintenance uses the linked runtime delivery owner; artifacts,
Issues, wave mechanics, and recurrence learning use their existing owners.
Before changing hook, monitoring, schedule, reference, or closeout tooling, cite
the evidence locator and verify that owner path. A missing summary is not
evidence for an invented cause.

Verify the selected owner gate. Rerun only the focused route/eval/check that
covers the changed behavior; a full dashboard run is useful only when the owner
needs accumulated post-change evidence. If the selected gate fails, preserve
`failing_contract`, `observation_level`, `cause_classification`,
`intent_preservation`, and `evidence` in the existing packet before changing
intent, reverting, weakening an oracle, or reducing validation. Keep
implementation bugs, specification or oracle mismatch, fixture/environment
issues, unrelated failures, and approved-design conflicts with their owner or
escalation path.

## Boundaries

Archive branch identity, legacy inventory, retention, and migration authority
belong to the `agent-canon-log` policy repository. This skill routes dashboard
evidence and does not duplicate those policy definitions.

- Raw log compaction and dashboard API schema belong to `$agent-log-analysis`
  and `generate_agent_runtime_dashboard.py`.
- Continuous delivery and retry belong to the existing runtime scheduler and
  archive publishers, as defined by the linked delivery owner. Do not replace
  them with per-task manual sync, a new daemon, or artifact-writeout duties.
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

The runtime discovery adapter delegates these clauses to this owner. Reuse one
existing summary or a bounded snapshot-qualified excerpt; missing or stale
evidence limits the claim and does not justify broad raw-log reads or automatic
sync, repair, or eval collection. When repair is selected, use the existing
Runtime Log Repair Packet and route the action through the owner named in
Required Flow. Analysis, artifact writeout, eval production, publication, and
retry remain with their respective owners.

Use the selected owner gate for closeout. Rerun a full dashboard only when that
owner needs accumulated post-change evidence. If the gate fails, keep
`failing_contract`, `observation_level`, `cause_classification`,
`intent_preservation`, and `evidence` with the existing packet before changing
repair intent, reverting, deleting intended behavior, weakening an oracle, or
downscoping validation. Route implementation, specification/oracle,
fixture/environment, unrelated, and approved-design conflicts to their owner,
residual, or escalation path.
