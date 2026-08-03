# OOP Responsibility Audit Unit
<!--
@dependency-start
contract design
responsibility Audits OOP responsibility, state ownership, helper boundaries, and readability evidence.
upstream design ../README.md owns audit unit boundaries
upstream design ../../design/codex-spark-implementation-routing.md owns implementation correspondence
upstream implementation ../../../agents/skills/oop-type-design.md owns OOP contract design
downstream implementation ../../../agents/skills/oop-readability-check.md owns mechanical readability evidence
@dependency-end
-->

## Reader Map

class、object、state、member、helper、wrapper の責務を type/design trace、呼び出し関係、
mechanical OOP report の順に読みます。可読性 tool の出力と reviewer judgement は別 evidence
として保持します。

## Owner Responsibility

`oop-type-design` が responsibility boundary を定義し、`oop-readability-check` が
mechanical inventory と readability evidence を所有します。

## Invariant

object が自身の invariant と state を所有し、不要な state/member/helper/wrapper、
責務の横取り、整形だけの抽象化、静的 tool の回避がない。実装 abstraction は design
contract と一致する。

## Evidence Sources

- type/design packet と implementation correspondence
- `oop/python/readability.py`
- `oop_rule_inventory.py`
- class/module dependency graph
- reviewer judgement と tool output の分離記録

## Repair Route

owner skill は `oop-type-design`、tooling は `oop-readability-check` の既存 inventory
と readability tool。責務を移す必要がある場合は design packet を先に更新し、writer に
bounded handoff します。

## Validation

対象 class/module の static inventory、責務/readability review、変更後 readback で必要十分
とします。runtime test は object invariant が静的に判定できない場合だけ owner unit の
最小 oracle を使います。

## Close Condition

各 object の state/operation owner が一意に説明でき、不要な abstraction がなく、tool
result と reviewer judgement が一致または差異を記録した状態で close する。

## Related Change Surfaces

`surface:code.oop-responsibility`、`surface:code.readability`、`surface:implementation.trace`。
class/type/responsibility boundary や OOP checker の契約変更時だけ本 unit を更新します。

## Scope Patterns

- `pattern:python/**`
- `pattern:cpp/**`
- `pattern:rust/**`
- `pattern:include/**`
- `pattern:tools/**`
- `pattern:tests/**`

## Legacy Migration IDs

PRA-C053 PRA-C071 PRA-C072 PRA-C073 PRA-C078 PRA-X042 PRA-X043
