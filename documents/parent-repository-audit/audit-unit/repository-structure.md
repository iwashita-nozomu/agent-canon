# Repository Structure Audit Unit
<!--
@dependency-start
contract design
responsibility Audits the complete tracked tree and directory responsibility boundaries.
upstream design ../README.md owns the parent audit surface and tracked-tree semantics
upstream design ../../structure/repo-structure-contract.toml owns expected repository structure
upstream implementation ../../../tools/agent_tools/parent_repository_audit.py enumerates tracked paths
downstream implementation ../../../agents/skills/structure-refactor.md repairs structure ownership
@dependency-end
-->

## Reader Map

repository structure contract と responsibility scope の path/kind evidence を読む unit
です。`git ls-files -z` の全 tree をこの unit の fallback pattern として再分類せず、
一般 path owner は `responsibility-scope.toml` に委譲します。

## Owner Responsibility

`structure-refactor` が親 repository の root、directory、README、submodule 境界を
所有します。`responsibility-scope.toml` が一般 path owner/class の唯一の source であり、
`repo_structure_contract.py` は required path の existence/kind だけを判定します。

## Invariant

structure contract の required path が存在し、kind が一致し、path escape がない。
submodule 内部は親 tree に混ぜず、generated report を source structure と誤認しない。
一般 path の owner/class と audit-unit の scope は別の二重正本にならない。

## Evidence Sources

- `documents/structure/repo-structure-contract.toml`
- `tools/agent_tools/repo_structure_contract.py`
- `tools/agent_tools/responsibility_scope.py`
- `tools/agent_tools/parent_repository_audit.py check`

## Repair Route

owner skill は `structure-refactor`、主 tool は `repo_structure_contract.py` と
`responsibility_scope.py`。missing/kind mismatch は structure contract を修正し、一般
path owner の判断は responsibility scope に追加して readback します。audit-unit の
pattern を `all-tracked` に広げる fallback は使いません。

## Validation

static structure contract と scope map で判定します。runtime build は構造 invariant を
静的に確定できない場合だけ、owner tool が指定した最小 command を実行します。

## Close Condition

structure contract と responsibility scope が pass し、修正後の対象 path readback が
同じ結果を返す。audit unit の overlap や全 tracked fallback を完了条件にしない。

## Related Change Surfaces

`surface:repo.structure`、`surface:responsibility.scope`。structure contract、directory
README、unit pattern のいずれかを変更した同じ PR でこの unit の関係を確認します。

## Scope Patterns

- `pattern:documents/structure/**`
- `pattern:responsibility-scope.toml`
- `pattern:README.md`
- `pattern:AGENTS.md`
- `pattern:ROOT_AGENTS.md`
- `pattern:.gitmodules`

## Legacy Migration IDs

この新設 unit に直接対応する legacy metadata、checkbox、command はありません。
legacy checklist の全 ID は他の owner unit へ一回だけ移行されています。
