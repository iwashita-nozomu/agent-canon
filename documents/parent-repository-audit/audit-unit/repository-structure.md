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

全 tracked tree の被覆と directory responsibility の入口を読む unit です。最初に
`git ls-files -z` と structure contract の結果を比較し、個別 owner unit の重複を
cross-reference として扱います。

## Owner Responsibility

`structure-refactor` が親 repository の root、directory、README、submodule境界、
responsibility scope を所有します。`repository-structure` は全 tracked path の
一次的な被覆判定を所有します。

## Invariant

親 root の全 tracked path が少なくとも一つの audit-unit pattern に決定論的に一致し、
path escape と不明な directory ownership がない。submodule 内部は親 tree に混ぜず、
generated report を source structure と誤認しない。

## Evidence Sources

- `git ls-files -z` の親 root readback
- `documents/structure/repo-structure-contract.toml`
- `tools/agent_tools/repo_structure_contract.py`
- `tools/agent_tools/responsibility_scope.py`
- `tools/agent_tools/parent_repository_audit.py check`

## Repair Route

owner skill は `structure-refactor`、主 tool は `repo_structure_contract.py` と
`responsibility_scope.py`。uncovered path はこの unit の pattern を無根拠に広げず、
実際の責務 owner を決めて該当 unit と directory README を修正し、親 root の readback
を再実行します。

## Validation

static structure contract、scope map、audit tool の uncovered/overlap packet で判定します。
runtime build は構造 invariant を静的に確定できない場合だけ、owner tool が指定した
最小 command を実行します。

## Close Condition

全 tracked path が被覆され、structure contract と responsibility scope が pass し、
overlap には primary owner と cross-reference があり、修正後の対象 path readback が
同じ結果を返す。

## Related Change Surfaces

`surface:repo.structure`、`surface:responsibility.scope`。structure contract、directory
README、unit pattern のいずれかを変更した同じ PR でこの unit の関係を確認します。

## Scope Patterns

- `pattern:all-tracked`

## Legacy Migration IDs

この新設 unit に直接対応する legacy metadata、checkbox、command はありません。
legacy checklist の全 ID は他の owner unit へ一回だけ移行されています。
