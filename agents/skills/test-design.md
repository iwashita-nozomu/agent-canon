# test-design
<!--
@dependency-start
contract skill
responsibility Documents test-design for this repository.
upstream design ../canonical/skills.md skill canon registry
@dependency-end
-->

## Reader Map

- Purpose: conditionally classifies unresolved oracle/specification/regression
  risk after the owning implementation mechanism exists.
- Use When: an explicit post-implementation risk remains outside static
  analysis, existing checkers, and targeted validation.
- Boundary: this skill does not gate ordinary code changes, bug fixes, parser
  changes, or validation failures by itself, and it does not weaken behavior to
  satisfy an existing test.

## Purpose

この skill は、production design / algorithm contract と owning implementation
mechanism が確立または修復された後に、既存の static analysis、checker、
formatter、dependency review、type checker、lint、docs check、targeted
validation が所有しない具体的な oracle / specification / regression /
failure-mode risk を分類します。既存 tests は contract、symptom、regression
placement の evidence であり、最初に tests を書き換える根拠ではありません。

## Activation Decision

最初の出力は必ず `Activation Decision` とします。

1. owning design / algorithm contract、public entrypoint、state transition または recurrence、invariant、stopping / acceptance rule、failure semantics、および code-side implementation mechanism が確立または修復済みか確認します。未確立なら `activation=deferred` として owning repair route を返し、test plan と tool run は要求しません。
1. concrete unresolved oracle、specification、regression、または failure-mode risk があるか確認します。ordinary code change、bug fix、parser change、validation failure、public behavior の変更だけでは activation の根拠にしません。
1. その risk が static validation、existing checker、formatter、dependency review、type checker、lint、docs check、または targeted validation の所有範囲外か確認します。該当しなければ `activation=not_needed` として canonical validation route だけを返し、test plan、test-design tool、test の変更を要求しません。
1. mechanism と unresolved risk の両方が残る場合だけ `activation=required` とし、以下の conditional checklist を適用します。

## Expected Outcome

- 常に `Activation Decision`、根拠、次の owner route を返す
- `activation=not_needed` または `activation=deferred` では `test_plan.md` と test-design tool run を必須にしない
- `activation=required` の場合だけ、static path survey、contract source、observation level、observable outcome、oracle、input space、adequacy evidence、nasty case、regression case、placement notes を具体化する
- checker-owned property は canonical static validation evidence に戻す
- tests は concrete behavior regression oracle がある場合だけ作成または編集する

## Conditional Checklist

`activation=required` の場合だけ実行します。

- code path と関連 test path を survey / placement evidence として記録し、API shape、private helper、return shape、error prose、mock order、internal call sequence を勝手に固定しない
- 関連 tests がある場合、既存の test-design checker を必要な範囲で実行し、finding を behavior contract と照合する。activation が false の場合は実行しない
- contract source、behavior contract、observation level、observable outcome、oracle、input space、adequacy evidence、Do Not Freeze を分ける
- malformed input、boundary value、empty / null-ish input、error path、state transition、再発しやすい regression を、安定した観測レベルで列挙する
- parser / formatter / graph / router / mapping では property または metamorphic relation を検討するが、checker-owned property は test oracle に昇格させない
- numerical、randomized、tolerance、solver、convergence、residual、benchmark、experiment-style test は、`documents/coding-conventions-testing.md` の Numerical Test Admission Gate を owner とし、`activation=required` かつ数値 trigger、non-numerical alternative、oracle、budget が approved route にある場合だけ提案する
- existing test style、fixture layout、naming を mirror し、test の追加・編集は concrete behavior regression oracle に限定する

## Validation Failure Response

test / check が失敗した場合、単純化、revert、feature / test deletion、oracle
weakening、intended behavior の削除、validation downscope に進む前に、
`failing_contract`、`observation_level`、`cause_classification`、
`intent_preservation`、`evidence` を記録します。slug set と route semantics は
`documents/runtime-profiles-and-check-matrix.json` が所有し、
`documents/runtime-profiles-and-check-matrix.md` は generated reader projection
として参照します。

`cause_classification=implementation_bug` で contract と oracle が安定している
場合は、approved intent を保ったまま owning code / config / docs / workflow
repair に戻します。失敗を pass にするため intent を弱めません。

## Common Failure Modes

- mechanism を直す前に tests や expected values を書き換える
- public behavior、コード変更、parser 変更、validation failure だけで role を起動する
- static checker の成功を execution-only test、no-crash test、pytest smoke で包む
- private helper、mock order、全文 error prose、internal call sequence を oracle にする
- coverage だけを adequacy とみなし、regression oracle を定義しない
- failing test の因果診断なしに intended behavior や oracle を弱める
