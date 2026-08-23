# Repository Structure Audit Unit
<!--
@dependency-start
contract design
responsibility Audits required repository path existence and filesystem kinds without duplicating path ownership.
upstream design ../README.md owns the parent audit surface and tracked-tree evidence semantics
upstream design ../../structure/repo-structure-contract.toml owns expected repository path existence and kinds
upstream design ../../../responsibility-scope.toml owns the canonical path owner/class relation
upstream implementation ../../../tools/agent_tools/parent_repository_audit.py enumerates semantic audit units
downstream implementation ../../../agents/skills/structure-refactor.md repairs structure ownership
@dependency-end
-->

## Reader Map

repository structure contract と responsibility scope の別々の関係を読みます。
`repo-structure-contract.toml` は path existence/kind、`responsibility-scope.toml` は
既存 tracked path の owner/class を所有し、audit unit はどちらも再分類しません。

## Owner Responsibility

`structure-refactor` が親 repository の root、directory、README、external source-clone 境界を
所有します。`responsibility-scope.toml` が一般 path owner/class の唯一の source であり、
`repo_structure_contract.py` は required/optional path の existence/kind だけを判定します。

## Invariant

structure contract の required path が存在し、kind が一致し、path escape がない。
external source clone 内部は親 tree に混ぜず、generated report を source structure と誤認しない。
一般 path の owner/class と audit-unit selection を別の path map として重複保存しない。

## Evidence Sources

- `documents/structure/repo-structure-contract.toml`
- `responsibility-scope.toml`
- `tools/agent_tools/repo_structure_contract.py`
- `tools/agent_tools/responsibility_scope.py`
- `tools/agent_tools/parent_repository_audit.py list`

## Repair Route

owner skill は `structure-refactor`、主 tool は `repo_structure_contract.py` と
`responsibility_scope.py`。missing/kind mismatch は structure contract を修正し、一般
path owner の判断は responsibility scope に追加して readback します。audit unit の
path pattern や all-tracked fallback は作りません。

## Validation

static structure contract と canonical scope map をそれぞれ一回判定します。runtime build は
構造 invariant を静的に確定できない場合だけ、owner tool が指定した最小 command を実行します。

## Close Condition

structure contract と responsibility scope が pass し、修正後の対象 path readback が
同じ結果を返す。audit unit の coverage/overlap を完了条件にしない。

## Related Change Surfaces

`surface:repo.structure`、`surface:responsibility.scope`。structure contract、directory
README、ownership relation のいずれかを変更した同じ PR でこの unit の関係を確認します。

## Legacy Migration IDs

この新設 unit に直接対応する legacy metadata、checkbox、command はありません。
legacy checklist の全 ID は他の owner unit へ一回だけ移行されています。
