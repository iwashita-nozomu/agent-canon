# Codex Bootstrap

<!--
@dependency-start
contract agent-runtime
responsibility Owns selected run bootstrap, goal state, and adaptive context materialization.
upstream design ./CODEX_WORKFLOW.md conditional task-phase reader map
upstream design ../../documents/design/entrypoint-owner-map.md document responsibility split
@dependency-end
-->

Use [Codex Workflow](CODEX_WORKFLOW.md) to select the current phase.

## Codex Goal Session State

利用者が goal 機能を明示的に求めたときに、合意した目的と完了条件を Codex のセッションに
設定します。作業範囲と次に行う操作は Git の差分と会話で引き継ぎます。
権限や完了の判断は [共通指示](../../ROOT_AGENTS.md#always-on-boundary) に従います。

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

## 4. Run Context

協調や再開には [Codex の協調手順](../COMMUNICATION_PROTOCOL.md#native-collaboration) を使います。
role は [task catalog](../task_catalog.yaml) の選択済み workflow から決め、委譲する場合は
[subagent-bootstrap](../skills/subagent-bootstrap.md#launch-and-handoff) に従います。
