# Codex Bootstrap

<!--
@dependency-start
contract agent-runtime
responsibility Owns selected run bootstrap, goal state, and adaptive context materialization.
upstream design ./CODEX_WORKFLOW.md conditional task-phase reader map
upstream design ../../documents/design/entrypoint-owner-map.md document responsibility split
@dependency-end
-->

Read the selected section for a selected route requiring a run bundle, goal state, or token adaptation.
Return to [Codex Workflow](CODEX_WORKFLOW.md) for phase selection; do not
load inactive phases or restart completed intake merely by following a link.

## Codex Goal Session State

Codex の goal は session runtime state として使い、repository に mirror file を作りません。

- stable な goal 機能は Codex runtime の既定を使い、shared config に feature flag を重ねません。
- user が goal-driven intent を示したが exact objective を渡していない場合は、parent が target-state-complete Objective を組み立てます。intake draft は read-only discovery として扱い、edit authorization は target-state-complete Objective と implementation handoff の固定後に開始します。
- coordination、resumption、または選択された workflow が durable lifecycle evidence を要求する場合だけ run bundle を materialize し、work unit と iteration state は `schedule.md`、実行結果と next action は `work_log.md`、acceptance は validation evidence に記録します。
- run bundle を選択しない task は semantic handoff または tool result で owner、replaceable unit、mechanism、validation route、unresolved branch を満たします。session goal の存在は write authorization、implementation readiness、closeout の追加 gate にしません。
- user が goal-driven task を指定した場合、session goal と実装計画は同じ objective と acceptance criteria を参照します。durable evidence が必要な場合は、その work breakdown を run bundle の `schedule.md` へ直接記録します。
- iteration の継続は `schedule.md` の open work、`work_log.md` の next action、未完了の validation evidence から判断します。session goal はその判断を表示できますが、repository state の正本にはしません。

## Token Observation And Adaptive Materialization

When the user asks to reduce token usage, or current session evidence shows
repeated context loading, duplicate agent decisions, oversized tool output, or
retry loops, apply `$tokens`.

- Start from the project model and topology config. Runtime evidence owns any
  later task/profile classification or profile change.
- Materialize one accountable child for the current decision. Add a specialist
  only when a distinct input artifact, review focus, and output decision exist.
- Context may be large. Remove duplicated or decision-irrelevant copies, not
  context required by request clauses, owner boundaries, or traceability.
- Keep `worker` as the implementation default. Select `spark_worker` only from
  the typed parent packet. Explicit bounded owner/path/validation requests may
  close through the selected write-capable child route when the typed route
  requires one.
- Attribute change with the existing session comparison, role evaluator, and
  runtime dashboard tools. Missing post-change runtime evidence remains
  `missing`; it is not inferred from fewer configured roles.

Token-saving changes context loading while preserving correctness gates. The
active gates are those selected by runtime profile and risk class.

## 4. Run Context

coordination、resumption、または選択された workflow が durable lifecycle evidence
を必要とするときだけ run bundle を使います。通常の作業は選択済み owner への
semantic handoff と、実際の native tool / child results で進めます。関連 owner への
Markdown 相対リンクは条件付き案内であり、リンク先すべてを読む義務ではありません。
selected Skill と適用される prerequisite は本文を EOF まで読みます。

`agents/task_catalog.yaml` と選択された workflow の説明から、必要な role と責務を
選びます。実際に child を起動した結果と、その child の完了結果を区別し、選択済み
workflow の既存記録へ結果や失敗を残します。monitor の状態だけで完了を推定しません。
既存 Eval または owner review は必要作業の欠落や不要な作業を評価できますが、経路の
違いだけでは失敗としません。

default model / reasoning authority は `agents/model_profiles.toml` の registry です。
`.codex/agents/*.toml` は runtime readback view です。選択済み role の model と
validation はその owner route に従います。

Adaptive Improvement Loop では、outer run の `experiment_change_loop.md` に `Extension Backlog` を持ち、各 extension で別の waterfall run-id を作ります。
次の extension へ進む前に、直前 extension で選択された `waterfall-gate-check`、review、`task-close`、および commit / push の判断・結果を完了させます。未選択の review artifact や full rerun は作りません。

Review, validation, and closeout follow the selected workflow's owner guidance.

包括的開発の固定 Codex stack:

- `requirements_organizer`
- `manager_reviewer`
- `literature_researcher`
- `execution_planner`
- `plan_reviewer`
- `detailed_designer`
- `detailed_design_reviewer`
- `document_flow_reviewer`
- `project_reviewer`
- `docs_workflow_steward`
- `prompt_config_reviewer`
- `python_reviewer`
- `cpp_reviewer`
- `worker`

cost を無視して review coverage を優先する run では、research-driven change と comprehensive development は `--full-team` を許可します。
