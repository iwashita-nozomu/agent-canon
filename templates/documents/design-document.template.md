<!--
@dependency-start
contract template
responsibility Provides the canonical structure for a design document.
upstream design ../../documents/design/README.md design-document ownership and reader route.
upstream design ../../documents/rule/README.md repository document filename and language rules.
downstream implementation README.md implements the approved boundary.
@dependency-end
-->

# <Design title>

この template は、設計判断を実装可能な責務境界へ変換するための正本雛形です。

## Dependency header sample

派生 repo で利用するときは、実際の implementation path に置き換えた dependency header を
この本文 sample から作成します。sample はこの template 自体の graph header ではありません。

```text
@dependency-start
downstream implementation <implementation-path> implements the approved boundary.
@dependency-end
```

## 責務

- この文書が正本として固定する契約、責務、型境界、依存方向、失敗意味論を記録する。
- 実装者、reviewer、保守者が同じ判断を再構築できる根拠と受入条件を残す。
- 設計提案と既存実装の事実を混同せず、未解決の選択肢を明示する。

## 読者 map

- **利用者 / requester**: 何が変わり、何が変わらないかを確認する。
- **実装者**: replaceable responsibility unit、公開境界、依存、side effect を実装する。
- **reviewer**: 根拠、敵対レビュー、代替案、受入条件を adjudicate する。
- **保守者**: 再構築手順、更新責任、非正本 artifact の扱いを確認する。

## 含む内容

authority、責務、OOP/type boundary、依存閉包、side effect と failure semantics、
複数の選択肢と棄却根拠、敵対レビュー、再構築手順、受入条件、evidence and
assumption ledger を含めます。実装詳細の羅列、未検証の性能主張、run-local log の
貼り付けは含めません。

## Authority and decision status

- canonical owner:
- governing request / issue / contract:
- decision status: `proposed` / `approved` / `superseded`:
- approval authority and date:
- source-of-truth paths:
- generated or non-canonical evidence paths:

## Target state and scope

### Target state

<!-- 変更後に利用者が観測できる契約を、実装手順ではなく状態として書く。 -->

- public entrypoint / input:
- state transition or recurrence:
- return / output projection:
- observable side effect:
- preconditions and invariants:
- stopping, acceptance, or typed failure rule:

### Scope and non-goals

- in scope:
- explicitly out of scope:
- compatibility or migration boundary:
- public behavior / schema impact:

## Responsibility and OOP/type boundary

| replaceable unit | owns | does not own | public capability / type | invariant |
| --- | --- | --- | --- | --- |
| `<unit>` | `<responsibility>` | `<boundary>` | `<type or protocol>` | `<invariant>` |

- owner object / module:
- collaborator interfaces:
- data ownership and lifetime:
- substitution boundary:
- invalid state that the type must make unrepresentable:
- test or checker that exercises this boundary:

## Dependency closure and effects

### Dependency direction

```text
request / caller -> public entrypoint -> owned unit -> collaborator -> external effect
```

- upstream design / contract:
- implementation source:
- downstream consumers:
- dependency edges that must change together:
- import, header, or runtime boundary:

### Side effects and failure semantics

| effect | owner | trigger | durable artifact / mutation | failure result | recovery or rollback |
| --- | --- | --- | --- | --- | --- |
| `<effect>` | `<unit>` | `<condition>` | `<path or none>` | `<typed result>` | `<action>` |

State what is preserved on failure, what is fail-closed, and which caller may retry.
Do not turn an environment limitation into a silent fallback or a test-only branch.

## Options and decision

Compare at least two viable options before selecting one.

| option | mechanism | benefits | costs / risks | dependency and effect impact | status |
| --- | --- | --- | --- | --- | --- |
| A: `<name>` | `<mechanism>` | `<benefit>` | `<risk>` | `<impact>` | selected / rejected |
| B: `<name>` | `<mechanism>` | `<benefit>` | `<risk>` | `<impact>` | selected / rejected |
| C: `<name>` | `<mechanism>` | `<benefit>` | `<risk>` | `<impact>` | optional |

- selected option:
- selection rule:
- rejected options and concrete rejection evidence:
- unresolved branch that could change owner, mechanism, or validation:

## Adversarial review

Review the selected design as if trying to break its boundary.

- hidden assumption or missing precondition:
- wrong owner / helper-sprawl risk:
- dependency cycle or public-surface leak:
- partial write, stale artifact, or rollback hazard:
- malformed input, timeout, resource exhaustion, or hostile caller:
- alternative that would pass a superficial test but violate the contract:
- reviewer decision: pass / revise / escalate:
- required repair before implementation:

## Reconstruction and implementation trace

- clean checkout / branch precondition:
- source paths and exact sections to read:
- implementation sequence:
- generated artifacts and their producer:
- command to reconstruct the design evidence:
- command to reconstruct the implementation state:
- expected clean/dirty and ownership checks:

## Acceptance and validation

| acceptance condition | evidence / oracle | command or review action | result |
| --- | --- | --- | --- |
| public contract | `<checker / reviewer>` | `<command>` | pending |
| responsibility boundary | `<checker / static evidence>` | `<command>` | pending |
| dependency closure | `<dependency review>` | `<command>` | pending |
| side effect / failure semantics | `<targeted scenario>` | `<command>` | pending |
| reconstruction | `<readback>` | `<command>` | pending |

- acceptance owner:
- required evidence artifact:
- known limitations:
- close condition:

## Evidence and assumption ledger

| id | kind | claim / assumption | source path and line | confidence | how falsified |
| --- | --- | --- | --- | --- | --- |
| E1 | observation / assumption | `<claim>` | `<path:line>` | high / medium / low | `<check>` |

この template を埋めた設計文書は、承認後に実装へ投影します。run-local report、
raw log、生成済み mirror はこの文書の正本ではありません。
