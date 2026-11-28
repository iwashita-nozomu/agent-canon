# task-routing
<!--
@dependency-start
contract skill
responsibility Selects one canonical skill route plus evidence-backed deferred candidates without duplicate routing state sets.
upstream design ../canonical/skills.md skill canon registry
upstream design ../../documents/design/tool-skill-routing-refactor.md short tool and skill naming policy
upstream design ../../documents/design/responsibility-rationale.md routing-state rationale
upstream design ./agent-orchestration.md owns later Decision Sufficiency and write-safety policy
downstream implementation ../../tools/runtime/dispatch/agent-canon/src/catalog/skill_routes.rs owns the native route selector
downstream implementation ../../tests/agent_tools/test_task_routing_fast_path.py validates packet-free ordinary routing
upstream design ./skill-dependencies.yaml owns typed skill prerequisites, successors, order, and parallel relations
downstream implementation ../../tools/runtime/dispatch/agent-canon/src/catalog/skill_routes.rs derives typed route and invocation order
downstream implementation ../../tools/runtime/dispatch/agent-canon/src/catalog/skill_dependency_graph.rs owns graph validation and projection
@dependency-end
-->

## Purpose

Choose the Skills and tools for the requested outcomes from a prompt, changed
paths, or explicit area.

## Canonical output

Routing has two authoritative concepts:

```text
SELECTED_SKILLS=<ordered skills that should execute now>
DEFERRED_CANDIDATES=<candidate skills + activation evidence still required>
```

`SELECTED_SKILLS` lists the Skills to use now. A deferred candidate activates
when its condition is met.

LCPの `DEFERRED_SKILLS` 境界は [`agent-orchestration.md#Local Capability Priority`](./agent-orchestration.md#local-capability-priority) を参照します。ここではskill candidateの状態だけを投影します。

Legacy output names are compatibility views of these two states. New callers
use the canonical selected and candidate states.

## Operation

Use the host provider directly when it owns the result. See
[Task Skill Sets](README.md#task-skill-sets) for AgentCanon responsibilities.

Use `tools/bin/agent-canon route --prompt ... --mode routing-only` or the
changed-path route. Pass `--mode repo-changing` for an explicitly authorized
edit. The default is read-only.

作業途中で新しい観測や要求変更が生じたら、変わった判断に必要な owner
guidance を読み直します。最初に解決した選択は、影響する前提が変わらない限り
そのまま使います。

For a selected operation backed by tools, use
[Skill and tool cooperation](agent-orchestration.md#skill-and-tool-cooperation)
to connect the selected owner's decision to actual tool inputs and returned evidence.

## In-flight skill reads

新しい条件が成立したら、必要な箇所を [担当文書から読む](agent-orchestration.md#owner-first-read-trace)
方法で確認します。`skill-document-reader` は長い文書から該当箇所を探すときに使えます。

| 作業中に成立した条件 | 依存する判断・操作の前に読む関連スキル |
| --- | --- |
| 新しい証拠で担当・スキル・reviewの選択を変える必要がある | [agent-orchestration](agent-orchestration.md#decision-order) で変更された判断だけを解決する |
| tool出力のfindingを修正判断や報告へ渡す | [tool-finding-report](tool-finding-report.md) でfindingと根拠を整理する |
| 過去の実行ログを解析し、原因や再発条件を判断する | [agent-log-analysis](agent-log-analysis.md) で必要な記録を読む |
| 観測した問題をIssueへ記録・更新する | [issue-finding-report](issue-finding-report.md) で既存Issueと公開範囲を確認する |
| 検証結果のartifactを保存・更新する | [result-artifact-writeout](result-artifact-writeout.md) で実在する結果と保存先を確認する |

解決したら得られた根拠と必要な変更だけを既存taskへ戻し、中断した操作から続けます。
担当が変わる場合は、該当する選択だけを更新します。

## Boundary

Selected Skills own execution and validation. Open a downstream implementation
reference when the selected decision needs its evidence.
