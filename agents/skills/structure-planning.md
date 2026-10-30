# structure-planning
<!--
@dependency-start
contract skill
responsibility Establishes necessary content structure before prose and resolves unsettled document/artifact topology.
upstream design ../../documents/design/responsibility-rationale.md structure and visualization activation rationale
upstream design ../../documents/rule/README.md document rule canon
upstream design ../../documents/conventions/common/05_docs.md document responsibility and reading-activation boundary
upstream design ../../documents/design/README.md design canon reader route
upstream design code-visualization.md sole public visualization owner and typed projection contract
downstream implementation ../../.codex/personal/skills/structure-planning/SKILL.md exposes this workflow as a runtime skill
downstream implementation ../../tools/runtime/lifecycle/task_close.py consumes document_split_decision when a structural decision actually occurs
downstream implementation ../../tools/runtime/dispatch/agent-canon/src/dependency_headers.rs validates this adapter dependency header
@dependency-end
-->

## Purpose

新規文書や構成に影響する改稿で、目的・読者・要求範囲に合う構成がまだなければ、本文より先に構成を決めます。
複数候補があるかどうかだけで構成作成の要否を判断しません。owner、canonical source、reader entry、split/merge、section topology、presentation topology、validation route の未決事項もここで扱います。

十分な既存構成は再利用し、構成を変えない bounded な wording/link/paragraph edit に新しい構成作成を要求しません。
依頼や既存 source が小さな成果物の十分な順序を定めている場合は、その構造を使い、別の outline を作りません。
文書が長いことだけでは起動しません。

## Before prose

1. 要求、読者、根拠と、既存の見出し・brief・outlineを照合する。必要な内容の役割・順序・根拠の対応が揃っていれば、その構成を使う。
2. 十分な構成がなければ、順序が自明でも本文前に短い構成メモか既存の見出しへ作成・補完する。依頼、source、既存の見出しに必要な順序・役割・根拠対応がすでにあれば、それを再利用し、別の outline へ重ねて記録しない。部分的な不足は該当部分だけ補う。未確認の結論・根拠は未確定と示し、構成を埋めるために創作しない。
3. 執筆ownerがこの構成に沿って本文を書く。同じ担当でよく、新たなhandoffを要求しない。執筆中に構造上の欠落が分かったら、影響する構成を更新して本文へ戻る。構成のみ・承認待ちの明示指示は守り、それ以外に一律の承認待ちを作らない。範囲・結果・主要方針や未決契約の判断は [Decision Order](agent-orchestration.md#decision-order) に従う。

通常の構成メモには独自DSL、graph、固定schema、別ファイル、全paragraphのmapを要求しません。

## Minimal structure decision

以下はowner/source、読取経路、split/merge、topologyやvalidationの具体的な選択が残る場合だけ適用します。通常の構成メモをこのrecordへ変換する必要はありません。

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

執筆ownerは本文前に有効な構成を確認し、不足する場合にこのskillへ接続します。experiment、slide、HTML、refactorのownerも、既存構成を再利用し、実際に残る構造上の判断にだけ適用します。
