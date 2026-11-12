# Codex Bootstrap

<!--
@dependency-start
contract agent-runtime
responsibility Owns selected run bootstrap, goal state, and adaptive context materialization.
upstream design ./CODEX_WORKFLOW.md conditional task-phase reader map
upstream design ../../documents/design/entrypoint-owner-map.md document responsibility split
@dependency-end
-->

Read the selected section for session goal state or token adaptation.
Return to [Codex Workflow](CODEX_WORKFLOW.md) for phase selection; do not
load inactive phases or restart completed intake merely by following a link.

## Codex Goal Session State

Codex の goal は session runtime state として使い、repository に mirror file を作りません。

- stable な goal 機能は Codex runtime の既定を使い、shared config に feature flag を重ねません。
- 利用者が goal 機能を明示的に求めた場合は、合意した目的と完了条件を設定します。
- 実行・協調・再開には Codex 標準の機能を使い、作業範囲と次の action は Git の差分と現在の会話で引き継ぎます。独自の run bundle、schedule、task contract、進捗ファイルは生成しません。
- handoff または tool result に、対象・修正単位・期待する結果・検証経路・未解決事項を載せます。role 設定、実験・証明の成果物、hook ログ、Eval 結果は各 owner の既存経路で扱います。
- session goal の存在は write authorization、implementation readiness、closeout の追加 gate にしません。goal 機能は利用者が明示的に求めた場合に使い、実装計画と同じ objective・acceptance を参照します。

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

coordination と再開には Codex 標準の機能を使い、選択済み owner への
handoff と、実際の native tool / child results で進めます。関連 owner への
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

Adaptive Improvement Loop では、合意した目的と変更単位を会話で保持し、各単位の実装・不要コードの確認・必要な検証を完了して進めます。

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
