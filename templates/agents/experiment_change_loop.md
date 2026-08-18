# Experiment Change Loop（実験変更ループ）
<!--
@dependency-start
contract template
responsibility Documents Experiment Change Loop for this repository.
upstream design ../../agents/canonical/ARTIFACT_PLACEMENT.md artifact placement contract
@dependency-end
-->


- Run ID: {\{RUN_ID}}
- Task: {\{TASK}}
- Owner: {\{OWNER}}
- Created At (UTC): {\{CREATED_AT}}

{{>reader_map}}

## Goal（目標）

- Question: <!-- 一文で記録します。 -->
- Comparison Target: <!-- baseline、main、external reference。 -->
- Exit Criteria: <!-- loop を閉じる前に何が成立している必要があるか。 -->
- Stop Budget: <!-- iteration count、runtime budget、stop condition。 -->
- Scope: <!-- 対象となる file、experiment topic、report。 -->

## Extension Backlog（拡張 backlog）

| Backlog ID | Extension | Why Now | Expected Effect | Risk | Waterfall Run ID | Status |
| ---------- | --------- | ------- | --------------- | ---- | ---------------- | ------ |

## Fixed Protocol（固定 protocol）

- Baseline Ref: <!-- commit、branch、run directory。 -->
- Metrics: <!-- primary metric と failure count。 -->
- Case Set: <!-- dimension、level、dtype、seed、dataset slice。 -->
- Fairness Notes: <!-- timeout、hardware、allocator、worker count、tuning rule。 -->
- Artifact Paths: <!-- result/<variant>/<run_name>/ と report path。 -->

## Iterations（反復）

| Iteration | Backlog ID | Extension | Waterfall Run ID | Waterfall Gate Evidence | Validation | Run Name / Path | Critical Review | Report Review | Decision | Next Action |
| --------- | ---------- | --------- | ---------------- | ----------------------- | ---------- | --------------- | --------------- | ------------- | -------- | ----------- |

## Current State（現在状態）

- Active Extension ID: <!-- 現在実行中の backlog ID。 -->
- Active Waterfall Run ID: <!-- current extension の reports/agents/<run-id>。 -->
- Active Decision: <!-- report_rewrite_required / extra_validation_required / rerun_required / direction_rethink_required / approved / backlog_continue / stop_without_merge -->
- Best Current Evidence: <!-- 短い事実要約だけ。 -->
- Remaining Risk: <!-- closure を妨げるもの。 -->

## Closeout Check（closeout 確認）

- 各 iteration は 1 つの backlog extension と 1 つの waterfall run id に対応します。
- 次の extension の開始前に、前の extension の waterfall pass を閉じます。
- latest baseline と changed run は同じ protocol を使います。
- quantitative summary を更新します。
- critical review outcome を記録します。
- report review outcome を記録します。
- next action または approved state を記録します。
