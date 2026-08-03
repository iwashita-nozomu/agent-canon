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

実装の public boundary、型、literal、helper、language-specific source を、design trace
と dependency header から読みます。既存 tool の静的結果を優先し、数値や `Any` を一律に
禁止せず、根拠と境界を確認します。

## Owner Responsibility

`oop-type-design` が責務と型境界を定義し、`python-review` / `cpp-review` が各言語の
実装と targeted validation を所有します。

## Invariant

数学的 object、algorithm、implementation boundary、public type が一致し、曖昧な
`Any`/`None` runtime 分岐、根拠のない hardcoded number、重複 helper、legacy wrapper
が新たな責務境界を作らない。

## Evidence Sources

- language source と public API/type declarations
- `documents/design/` の implementation trace
- `check_static_any.py`、`check_hardcoded_numbers.py`
- `oop_rule_inventory.py` と dependency graph
- reviewer が確認した責務境界

## Repair Route

owner skill は `oop-type-design`、language repair は `python-review` または `cpp-review`。
tool は既存 static-any、hardcoded-number、dependency checker を使い、既存 option/adapter
で足りない場合だけ design issue として戻します。

## Validation

型境界、dependency direction、対象 static checker、変更言語の最小 native validation を
必要十分とします。未変更言語の全 suite や Docker build は実行しません。

## Close Condition

型と責務の design trace が実装に対応し、static finding が解消または根拠付きで分類され、
対象 source の readback と選択された validator が pass する。

## Related Change Surfaces

`surface:code.type-boundary`、`surface:implementation.trace`、`surface:language.python`、
`surface:language.native`。public API、型、algorithm boundary、static checker の契約変更時
だけ本 unit を更新します。

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

PRA-C052 PRA-C054 PRA-C074 PRA-C075 PRA-C076 PRA-C077 PRA-X032 PRA-X033 PRA-X040 PRA-X041 PRA-X044
