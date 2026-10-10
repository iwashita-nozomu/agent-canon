# tool-finding-report

<!--
@dependency-start
contract skill
responsibility Documents tool-finding-report for this repository.
upstream design ../canonical/skills.md skill canon registry
upstream design result-artifact-writeout.md raw result and summary artifact policy
upstream design report-writing.md reader-facing evidence report policy
downstream design refactor-loop.md consumes finding packets for repair slices
downstream implementation ../../.codex/personal/skills/tool-finding-report/SKILL.md exposes this workflow as a runtime skill
@dependency-end
-->

## Reader Map

- Purpose: use selected tools to produce complete findings for the chosen scope,
  ranking them when the request or repair decision needs prioritization.
- Section path: Purpose, Use When, and Boundary define ownership; Finding Packet
  and Procedure define selected artifacts and conditional ranking; Refactor
  Integration explains how repair workflows consume the packet.
- Use when: baseline findings, mechanical priority order, before/after impact,
  or prompt-feedback evidence is needed before or after implementation.
- Boundary: this skill reports findings and ranks them when needed; repair
  choice belongs to the caller workflow, `refactor-loop`, or the relevant
  implementation skill.

## Purpose

tool、checker、hook、static analysis、構造解析を使って選択した scope の問題を探します。
raw result と structured artifact は依頼や handoff が必要とするときにまとめ、mechanical
priority order、reader-facing report、before / after impact は依頼または repair/handoff の
判断が必要とするときに加えます。

この skill は実装修正を担当しません。実装は `refactor-loop`、通常 task execution、
または該当 workflow が担当し、この skill の finding packet を入力にします。

## Use When

- user が tool で問題を探して報告するよう求めたとき
- refactor / implementation の前に full baseline finding と mechanical priority order
  を固定するとき
- 実装後に finding が増えたか、priority が悪化したかを見たいとき
- tool / hook / reviewer / subagent feedback を、次の handoff prompt や shared
  skill / workflow prompt に戻す必要があるとき

## Boundary

- raw result、summary artifact、manifest、overwrite policy は
  `result-artifact-writeout` の責務です。
- reader-facing な narrative report、limitations、claim strength は
  `report-writing` の責務です。
- behavior-preserving な実装修正、repair slice、review gate、実際にどれを直すかの
  取捨選択は `refactor-loop` または呼び出し元 workflow の責務です。
- この skill は finding を自動で「削除対象」とは扱いません。tool は候補と根拠を
  出し、実装側が責務境界、数理契約、API 契約を見て採否を決めます。

## Finding Packet

Normalize findings through the host GitHub adapter
`tools/repository/github/issue_sync.py` when an Issue handoff requires it. Use
the request, changed paths, or current owner boundary to select scope; use
`repo-wide` only when requested or authorized by the parent scope and needed to
answer the question. Preserve every result within the selected scope. Group identical
owner/root-cause/fix records once and retain their evidence paths. A warning is
a closeout obligation only when it is actionable or blocking.

tool finding report は、選択した scope の finding を一つの packet にまとめます。
この skill は scope 内の finding を勝手に削らず、repair slice や実際の修正対象は
上位 workflow が選びます。mechanical priority order は、依頼または repair decision
が順位付けを必要とするときに作ります。

以下の packet fields は選択した結果と handoff に必要なものを使います。
inactive な比較、priority、warning、prompt feedback の空 placeholder は作りません。
既存の downstream schema を使う場合は、その schema の必須値を維持します。

- `scope`: selected path/range, baseline ref, excludes, dependency roots; `repo-wide`
  scope の要求または decision need があればその根拠も残す
- `commands`: 実行 command、cwd、exit status、tool version または commit
- `raw_artifacts`: tool の raw text / JSON / JSONL
- `structured_artifacts`: 正規化 JSON、full table、summary
- `impact_artifacts`: before / after comparison、added / removed finding。比較が明示
  されたときだけ作る補助 artifact
- `mechanical_summary`: count and full finding table for the selected scope;
  include mechanical priority order and actionability signals when ranking is
  needed
- `tool_warning_ledger`: actionable/blocking warning に継続が必要な場合だけ、
  owner、status、repair/evidence route を記録する。非 blocking warning は
  closeout gate にせず、必要なら raw output に残す
- `priority_policy`: deterministic ranking inputs and weights when this run ranks
  findings
- `interpretation`: agent の解釈。観測事実と推論を分ける
- `prompt_feedback_decision`: `not_required`、`handoff_prompt_gap`、
  `shared_skill_or_workflow_gap`、`tool_gap`、`test_or_design_gap`
- `handoff_boundary`: this skill reports findings and ranks them when needed;
  the consumer skill decides repair slices, implementation, deferral, or
  prompt/tool repair

## Procedure

Select only the steps that can affect the requested result. When deriving a
structured artifact, retain its source result first; ranking, narrative
reporting, warning tracking, and prompt feedback are conditional decisions, not
stages every tool run must complete.

1. Select scope from the request, parent scope, changed paths, and decision need.
   Use repo-wide scope only when authorized by that scope and needed to answer
   the question. Record the selected paths and excludes; set a comparison ref or
   worktree only for an explicit before/after question.
1. When the requested report, persistence owner, or implementation handoff needs
   a durable raw result, save it first with `result-artifact-writeout`. Preserve
   failed or partial output when it bears on that decision.
   failed validation / check output を implementation に渡す場合は、
   validation-failure-response packet の `failing_contract`、
   `observation_level`、`cause_classification`、`intent_preservation`、
   `evidence` を finding packet に含めます。
1. Create the structured artifacts for the selected tool families and scope.
   Do not truncate results within that scope; omit unrelated tool families.
   - Python structural analysis: `python-structure-hash` ->
     `python-structure-hash-report`
   - Python structural planning: `python-structure-hash-scope-plan` after
     dependency review exists; this creates the full Change Impact Packet with
     `impact_blocks`, `scope_candidates`, `selected_scope`, and
     `repair_batches`
   - Before / after diff: `python-structure-hash-impact`。比較が明示されたときだけ使う
   - Algorithm modules: `python-algorithm-contract-check`
   - Module groups: `python-module-groups-check`
   - OOP readability: `tools/oop/<language>/readability.py --format json`
   - Dependency surface: `run_repo_dependency_review.sh` and related manifest tools
1. When priority order is requested or needed to choose repair work, rank the
   selected findings using the relevant available signals and retain the ranking
   rule. Otherwise preserve the tool's ordering and report whether it supplied
   priority.
1. report では機械結果と agent interpretation を分けます。reader-facing report に
   する場合は `report-writing` を使います。
   - user が「レポート」「まとめ」「結果を解釈」「Markdown にして」などを求めた場合、
     `report-writing` は必須です。validation summary、command log、top-N excerpt、
     raw JSON path だけで closeout してはいけません。
   - Use `structure-planning` before drafting when the report has an unresolved
     reader-flow or comparison decision; a nontrivial finding packet alone does
     not require a separate structure contract.
   - report は full structured artifact を参照してよいですが、underlying artifact
     は削らず、report 側に full table の保存先と取捨選択境界を明記します。
1. finding を分類します。
   - `implementation_bug`: 実装を直す
   - `missing_test_or_design_evidence`: test / design artifact を直す
   - `missing_design_claim_evidence`: design claim を code、dependency header、parent-doc evidence に接続する
   - `handoff_prompt_gap`: 次の subagent handoff prompt を直す
   - `shared_skill_or_workflow_gap`: skill / workflow / task catalog prompt を直す
   - `tool_gap`: tool rule、false positive、structured output を直す
   - `review_required`: 機械判定だけでは採否を決めない
1. Track a warning through its existing owner when it is actionable or blocks a
   requested guarantee. A non-blocking warning that does not affect the decision
   can remain in raw output without creating a new closeout obligation. When a
   run bundle owns warning tracking, use its existing `Tool Warnings` route and
   [template](../../templates/agents/workflow_monitoring.md).

```bash
python3 tools/runtime/lifecycle/workflow_monitor.py \
  --report-dir reports/agents/<run-id> \
  --tool-warning "warning_id=<stable-id> source_tool=<tool> severity=<warning|fix-now|s0|s1> status=open message=<short-no-spaces> repair_command=<command-or-doc>"
```

   An actionable warning that is being tracked is updated after repair with its
   existing evidence. A blocking warning remains open until its owner resolves
   it. Non-actionable warnings do not need a disposition. Report an explicit
   no-warning status only when the active run-bundle contract requests one.

```bash
python3 tools/runtime/lifecycle/workflow_monitor.py \
  --report-dir reports/agents/<run-id> \
  --tool-warning-status none
```

Use this no-warning command only when the active run-bundle owner requires that
readback.
1. `handoff_prompt_gap` または `shared_skill_or_workflow_gap` は、次の
   write-capable subagent を起動する前に prompt を修正します。closeout へ先送り
   しません。
1. Record prompt feedback in the run bundle only when evidence establishes a
   reusable handoff, skill/workflow, tool, test, or design gap. No feedback
   record is needed for an ordinary resolved finding.

```bash
python3 tools/runtime/lifecycle/workflow_monitor.py \
  --report-dir reports/agents/<run-id> \
  --runtime-feedback "source=<tool|hook|reviewer|subagent|user> target=<skill-or-workflow-or-handoff> action=prompt_repair reason=<short-reason>"
```

## Refactor Integration

When the selected findings drive a refactor, `refactor-loop` consumes this
packet. Capture a baseline when it can distinguish the change, and rerun only
the tools whose evidence can show whether the changed contract or next repair
decision moved. Create before/after impact only when that comparison is
requested. Preserve findings in the selected scope; the caller chooses which
ones to repair.

For a write-capable handoff, carry the packet path and the current repair
boundary, including forbidden semantic changes and any established new-finding
constraint. Include prompt feedback only when a prompt gap was found.

## Runtime Contract Clauses

The runtime discovery adapter delegates these required operating clauses to this canonical owner.

Use `Finding Packet`, `Procedure`, and `Refactor Integration` according to the
request and the selected consumer. Choose the scope, tool families, ranking, and
durable artifacts from the question and handoff need; preserve all findings in
the selected scope. Use the existing validation-failure-response or
dependency-analysis packet when a finding is handed to implementation or
planning. Track actionable warnings and reusable prompt/tool gaps only through
an active owner that needs that evidence. Use `report-writing` for a requested
reader-facing report, and `structure-planning` only for an unresolved structure
decision. Repair selection remains with the caller.
