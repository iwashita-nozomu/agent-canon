# Code And Type Boundary Audit Unit
<!--
@dependency-start
contract design
responsibility Audits code structure, public type boundaries, static Any, literals, and language ownership.
upstream design ../README.md owns static-first audit policy
upstream design ../../design/codex-spark-implementation-routing.md owns implementation trace
upstream implementation ../../../agents/skills/oop-type-design.md owns type and responsibility design
downstream implementation ../../../agents/skills/python-review.md and ../../../agents/skills/cpp-review.md own language repair
@dependency-end
-->

## Reader Map

実装の public boundary、型、literal、helper、object の state ownership、language-specific
source を、design trace と dependency header から読みます。既存 tool の静的結果を優先し、
数値や `Any` を一律に禁止せず、根拠と境界を確認します。

## Owner Responsibility

`oop-type-design` が責務・object invariant・型境界を一つの implementation/verification
path として定義し、`oop-readability-check` と `python-review` / `cpp-review` がその
同じ path の機械的 evidence と各言語 validation を所有します。OOP を別の audit unit
や別の ownership manifest として重複列挙しません。

## Invariant

数学的 object、algorithm、implementation boundary、public type、object state/operation
owner が一致し、曖昧な `Any`/`None` runtime 分岐、根拠のない hardcoded number、重複
helper、legacy wrapper が新たな責務境界を作らない。mechanical OOP report と reviewer
judgement は同じ対象に対する補完 evidence として記録します。

## Evidence Sources

- language source と public API/type declarations
- `documents/design/` の implementation trace
- `check_static_any.py`、`check_hardcoded_numbers.py`
- `oop_rule_inventory.py` と dependency graph
- `oop-readability-check` の対象 report
- reviewer が確認した責務境界、state ownership、helper boundary

## Repair Route

owner skill は `oop-type-design`、mechanical evidence は `oop-readability-check`、language
repair は `python-review` または `cpp-review`。tool は既存 static-any、hardcoded-number、
dependency checker を使い、既存 option/adapter で足りない場合だけ design issue として
戻します。

## Validation

型境界、object responsibility、dependency direction、対象 static checker、OOP report、
変更言語の最小 native validation を必要十分とします。未変更言語の全 suite や Docker
build は実行しません。

## Close Condition

型・OOP 責務の design trace が実装に対応し、static finding が解消または根拠付きで分類
され、mechanical OOP evidence と reviewer judgement の対象が一致し、対象 source の
readback と選択された validator が pass する。

## Related Change Surfaces

`surface:code.type-boundary`、`surface:code.oop-responsibility`、`surface:implementation.trace`、
`surface:language.python`、`surface:language.native`。public API、型、algorithm boundary、
OOP checker の契約変更時だけ本 unit を更新します。

## Scope Patterns

- `pattern:python/**`
- `pattern:cpp/**`
- `pattern:rust/**`
- `pattern:include/**`
- `pattern:tools/**`
- `pattern:scripts/**`
- `pattern:pyproject.toml`
- `pattern:pyrightconfig.json`
- `pattern:Makefile`

## Legacy Migration IDs

PRA-C052 PRA-C053 PRA-C054 PRA-C071 PRA-C072 PRA-C073 PRA-C074 PRA-C075 PRA-C076 PRA-C077 PRA-C078 PRA-X032 PRA-X033 PRA-X040 PRA-X041 PRA-X042 PRA-X043 PRA-X044
