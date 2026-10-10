# task-routing
<!--
@dependency-start
contract skill
responsibility Selects one canonical skill route plus evidence-backed deferred candidates without duplicate routing state sets.
upstream design ../canonical/skills.md skill canon registry
upstream design ../../documents/design/tool-skill-routing-refactor.md short tool and skill naming policy
upstream design ../../documents/design/responsibility-rationale.md routing-state rationale
upstream design ./agent-orchestration.md owns later Decision Sufficiency and write-safety policy
downstream implementation ../../tools/agent/orchestration/route.py selects short routing areas
downstream implementation ../../tests/agent_tools/test_task_routing_fast_path.py validates packet-free ordinary routing
upstream design ./skill-dependencies.yaml owns typed skill prerequisites, successors, order, and parallel relations
downstream implementation ../../tools/agent/skills/skill_route_catalog.py derives invocation order
downstream implementation ../../tools/agent/skills/skill_dependency_map.py validates and generates dependency graph
@dependency-end
-->

## Purpose

Choose the minimum skill/tool route from a prompt, changed paths, or explicit area. Ordinary routing does not require a Decision Sufficiency packet; later high-risk or genuinely ambiguous implementation owners may invoke that policy through `agent-orchestration`.

## Canonical output

Routing has two authoritative concepts:

```text
SELECTED_SKILLS=<ordered skills that should execute now>
DEFERRED_CANDIDATES=<candidate skills + activation evidence still required>
```

`SELECTED_SKILLS` is the one source of truth for execution. Deferred candidates do not execute until their evidence becomes true. Selecting a Skill does not activate every branch inside it.

LCPの `DEFERRED_SKILLS` 境界は [`agent-orchestration.md#Local Capability Priority`](./agent-orchestration.md#local-capability-priority) を参照します。ここではskill candidateの状態だけを投影します。

Historical names such as `SKILLS`, `ACTIVE_SKILLS`, `MATCHED_SKILLS`, `RELATED_SKILLS`, or `RELATED_SKILL_CANDIDATES` may be accepted as compatibility reads while callers migrate, but they are not independent state owners. New consumers read only the canonical selected/candidate state. If compatibility projections are emitted, they must be derived from the canonical state and may not carry extra routing meaning.

## Operation

Use `python3 tools/agent/orchestration/route.py --prompt ... --mode routing-only` or the canonical changed-path route. The caller must pass `--mode repo-changing` for an explicitly authorized edit; omitted mode remains non-write. Select the smallest owner set whose responsibilities are reachable from the request. Add a candidate only with a concrete activation condition; do not execute candidates preemptively or replace routing with another classifier/handoff schema.

作業途中で新しい観測や要求変更が生じたら、変わった判断に必要な owner
guidance を読み直します。最初に解決した選択は、影響する前提が変わらない限り
そのまま使います。

## In-flight skill reads

呼び出し元スキルの操作中に新しい条件が成立したら、その判断や操作に必要な
owner guidance を使う前に確認します。同一文書内の分岐やリンク先は、現在の条件と
委譲された責務から選びます。inactive な説明まで網羅せず、既に確認した有効な文脈は
再利用します。`skill-document-reader` は長い文書から必要箇所を探す補助にできますが、
EOF metadata は実際に内容を理解・適用した証明ではなく、必須の admission gate でも
ありません。新しい読込台帳や承認段階は作りません。

このスキルから既存候補へ渡す判断点は次のとおりです。個別作業の条件はその呼び出し元に
置き、候補辞書や選択状態の第二の正本にしません。

| 作業中に成立した条件 | 依存する判断・操作の前に読む関連スキル |
| --- | --- |
| 新しい証拠で担当・スキル・reviewの選択を変える必要がある | [agent-orchestration](agent-orchestration.md#decision-order) で変更された判断だけを解決する |
| tool出力のfindingを修正判断や報告へ渡す | [tool-finding-report](tool-finding-report.md) でfindingと根拠を整理する |
| 過去の実行ログを解析し、原因や再発条件を判断する | [agent-log-analysis](agent-log-analysis.md) で必要な記録を読む |
| 観測した問題をIssueへ記録・更新する | [issue-finding-report](issue-finding-report.md) で既存Issueと公開範囲を確認する |
| 検証結果のartifactを保存・更新する | [result-artifact-writeout](result-artifact-writeout.md) で実在する結果と保存先を確認する |

解決したら得られた根拠と必要な変更だけを既存taskへ戻し、中断した操作から続けます。
既知のリンク先は直接使い、担当が未解決の場合だけ既存routeで選択します。
`SELECTED_SKILLS` / `DEFERRED_CANDIDATES` は必要な変更だけを反映し、全体のroutingを
やり直しません。読むこと自体は修復、公開、追加検証、環境変更、委譲の権限を増やしません。

## Boundary

Routing chooses owners; selected skills own their execution and validation. The full LCP policy is owned by [`agent-orchestration.md#Local Capability Priority`](./agent-orchestration.md#local-capability-priority). `DEFERRED_SKILLS` remains a skill candidate projection, not operation disposition.
Before an implementation decision, use the selected Skill and its actual
delegated owners to understand the applicable contract. A `downstream
implementation` edge is opened when the active owner route needs that evidence;
the existence of a link or reader-tool record does not itself settle the decision.
