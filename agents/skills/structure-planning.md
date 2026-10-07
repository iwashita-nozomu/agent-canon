# structure-planning
<!--
@dependency-start
contract skill
responsibility Plans document/artifact topology only when owner, reader, source-of-truth, split/merge, or validation topology is genuinely undecided.
upstream design ../../documents/design/responsibility-rationale.md structure and visualization activation rationale
upstream design ../../documents/rule/README.md document rule canon
upstream design ../../documents/conventions/common/05_docs.md document responsibility and reading-activation boundary
upstream design ../../documents/design/README.md design canon reader route
upstream design code-visualization.md sole public visualization owner and typed projection contract
downstream implementation ../../.codex/personal/skills/structure-planning/SKILL.md exposes this workflow as a runtime skill
downstream implementation ../../tools/runtime/lifecycle/task_close.py consumes document_split_decision when a structural decision actually occurs
downstream implementation ../../tools/validation/semantic/dependencies/check_dependency_headers.py validates this adapter dependency header
@dependency-end
-->

## Purpose

owner、canonical source、reader entry、split/merge、section topology、presentation topology、または validation route に複数の候補があるときだけ構造を決めます。
bounded な wording/link/paragraph edit、既に順序が明らかな section、長いだけの文書には起動しません。

## Minimal structure decision

1. 既存 owner と caller の条件を読み、`structure_kind`、`audience`、`decision_context`、`owner_and_source` を決める。
2. `selected_topology`、`source_map`、material な `invalid_interpretations`、`validation_route` だけを既存の structure record に記録する。
   split/merge/rename/inline/keep が関わるときも、サイズ・token 数・一時都合を根拠にしない。
3. state/ownership/dependency/routing が図で明瞭になる場合だけ `code-visualization` に rendering/readback を委譲する。単純な prose/table で足りるなら図を作らない。
4. experiment plan では hypothesis/input/method/environment/metric/output/reproducibility の owner を固定し、stateful object や factory boundary が実際のリスクのときだけ OOP map を追加する。
5. 直接 review で解けない ordering/bridge 問題だけ semantic-index または prose-reasoning-graph を advisory に使う。
6. closeout では選択した owner/source、topology、source map、invalid interpretation、validation route を読み返す。通常の bounded edit はこの packet を作らず owner skill の check で閉じる。

## Minimal record

```text
structure_kind=<document|report|experiment|presentation|html|refactor|other>
audience=<reader>
decision_context=<decision supported>
owner_and_source=<canonical owner/source>
selected_topology=<ordered units or structural delta>
source_map=<source -> affected unit/claim>
invalid_interpretations=<material forbidden readings>
validation_route=<owner/check>
```

`report-writing`、experiment、slide、HTML、refactor owner は、実際の structural choice がある場合だけこの skill を呼びます。
