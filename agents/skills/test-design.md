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
`activation=required` では、owning design / contract の該当する設計条項と
code-side implementation mechanism（public entrypoint、分岐、parser、error
path、state transition、return projection）を同じ調査記録に結び付けます。各
候補 case は、`Design Clause -> Reachable Implementation Mechanism -> Concrete
Breaking Input/State Sequence -> Observable Outcome -> Decidable Oracle` の trace
を持ち、tests だけから contract や oracle を推測しません。

## Activation Decision

最初の出力は必ず `Activation Decision` とします。これはskill起動後の分類結果で
あり、skillを起動しないための事前ゲートではありません。選択されたらまず分類を
完了し、`activation=required` の場合は過剰なケースを増やさずに下記の後段設計へ
進みます。

1. owning design / algorithm contract、public entrypoint、state transition または recurrence、invariant、stopping / acceptance rule、failure semantics、および code-side implementation mechanism が確立または修復済みか確認します。未確立なら `activation=deferred` として owning repair route を返し、test plan と tool run は要求しません。
1. concrete unresolved oracle、specification、regression、または failure-mode risk があるか確認します。ordinary code change、bug fix、parser change、validation failure、public behavior の変更だけでは、テストを無制限に増やす根拠にしません。
1. その risk が static validation、existing checker、formatter、dependency review、type checker、lint、docs check、または targeted validation の所有範囲外か確認します。該当しなければ `activation=not_needed` として canonical validation route だけを返し、test plan、test-design tool、test の変更を要求しません。
1. mechanism と unresolved risk の両方が残る場合だけ `activation=required` とし、以下の conditional checklist を適用します。

## Test Admission Boundary

テストを設計する前に、対象propertyのboundary classを決めます。

- `necessary_presence`: 必要なディレクトリ、ファイル、リンク、型、設定、または参照の存在。path・link・manifest・parser・type checkerなど、既存の静的検査で観測できるものはテストにしません。
- `forbidden_presence`: 旧ラッパー、削除済み経路、禁止された重複実装、または明示された不許可surfaceの不在。存在禁止の検査は対象pathのabsence checkerで閉じ、実行テストへ昇格させません。
- `sufficient_behavior`: 公開behavior、状態遷移、数理特性、error semantics、またはreader-facing outcomeの成立。owner contractがこの成立を要求し、静的解析・既存checker・targeted validationで閉じない未解決oracleがある場合だけ、`activation=required` のテストへ進みます。

必要条件の充足は十分条件ではなく、禁止条件の不在も十分条件ではありません。
逆に十分条件を要求していない構造・移行・format変更へ、完全一致、no-crash、
実行成功、網羅性、またはAPIの内部形状を追加のoracleとして固定しません。
テストを提案する場合は `boundary_class`、failure predicate、owner contract、
観測レベル、既存checkerで閉じない理由を先に記録し、どれかが欠ければ
`activation=not_needed` または `activation=deferred` に戻します。

## Expected Outcome

- 常に `Activation Decision`、根拠、次の owner route を返す
- `activation=not_needed` または `activation=deferred` では `test_plan.md` と test-design tool run を必須にしない
- `activation=required` の場合だけ、static path survey、contract source、observation level、observable outcome、oracle、input space、adequacy evidence、nasty case、regression case、placement notes を具体化する
- `activation=required` の各 nasty / regression case は、設計条項、到達可能な実装機構、具体的な破綻入力または state sequence、observable outcome、判定可能な oracle の trace を持つ。いずれかが欠ける case は test-design の evidence として受理しない
- 各候補 case について、契約・型制約・既存 checker が「その case は起きない」とする null hypothesis を先に明記し、公開入力面または公開 state sequence から reachability witness を探す。witness が null hypothesis を反証しない、または存在しない場合は test 化せず、checker / static validation / owning design の境界へ戻す
- checker-owned property は canonical static validation evidence に戻す
- tests は concrete behavior regression oracle がある場合だけ作成または編集する

## Post-Activation Test Budget

`activation=required` は、テストスイート全体の網羅化や全checkerの再実行を意味しません。
未解決riskごとに最小の安定した観測レベルを一つ選び、同じ契約を確認する重複ケース、
実行できることだけを見るno-crashケース、内部helperや行数を固定するケースは追加しません。
一つのケースが複数のriskを覆う場合は、それを明示してケースを増やさないようにします。
ケース追加の前に、既存ケース・static checker・targeted validationで同じoracleが
閉じていないことを確認し、閉じていれば新規testではなく既存evidenceを参照します。

## Conditional Checklist

`activation=required` の場合だけ実行します。

- code path と関連 test path を survey / placement evidence として記録し、API shape、private helper、return shape、error prose、mock order、internal call sequence を勝手に固定しない
- owning design / contract の該当条項と code-side implementation mechanism を結び付け、public entrypoint から分岐・parser・error path・state transition・return projection までを確認する。tests だけから contract や oracle を推測しない
- 関連 tests がある場合、既存の test-design checker を必要な範囲で実行し、finding を behavior contract と照合する。activation が false の場合は実行しない
- contract source、behavior contract、observation level、observable outcome、oracle、input space、adequacy evidence、Do Not Freeze を分ける
- malformed input、boundary value、empty / null-ish input、error path、state transition、再発しやすい regression を、安定した観測レベルで列挙する
- 各 nasty / regression case は、設計条項から到達可能な実装機構を経て、具体的な breaking input / state sequence が observable outcome と decidable oracle に至る一つの trace として固定する。テスト件数や coverage を増やすこと自体を adequacy としない
- 各候補 case の null hypothesis と、その根拠である契約・型制約・checker を記録し、公開入力または公開 state sequence の reachability witness が null hypothesis を反証することを確認する。反証できない case は test-design の候補から外し、所有する checker / static validation / design route に返す
- parser / formatter / graph / router / mapping では property または metamorphic relation を検討するが、checker-owned property は test oracle に昇格させない
- numerical、randomized、tolerance、solver、convergence、residual、benchmark、experiment-style test は、`documents/conventions/coding-conventions-testing.md` の Numerical Test Admission Gate を owner とし、`activation=required` かつ数値 trigger、non-numerical alternative、oracle、budget が approved route にある場合だけ提案する
- existing test style、fixture layout、naming を mirror し、test の追加・編集は concrete behavior regression oracle に限定する

## Validation Failure Response

test / check が失敗した場合、単純化、revert、feature / test deletion、oracle
weakening、intended behavior の削除、validation downscope に進む前に、
`failing_contract`、`observation_level`、`cause_classification`、
`intent_preservation`、`evidence` を記録します。slug set と route semantics は
`documents/runtime/runtime-profiles-and-check-matrix.json` が所有し、
`documents/runtime/runtime-profiles-and-check-matrix.md` は generated reader projection
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

## Runtime Contract Clauses

The runtime discovery adapter delegates these required operating clauses to this canonical owner.

1. Read `agents/skills/test-design.md` and return `Activation Decision` first. This is
   a post-start classification, not a pre-start gate; once selected, run the
   classification before deciding the test cases.
1. Confirm that the owning production design / algorithm contract and implementation mechanism are established or repaired. If not, return `activation=deferred` with the owning repair route; do not run tools or require `test_plan.md`.
1. Confirm a concrete unresolved oracle, specification, regression, or failure-mode risk remains outside static analysis, existing checkers, and targeted validation. Ordinary code changes, bug fixes, parser changes, and validation failures alone do not justify unlimited test creation.
1. If the risk is absent or checker-owned, return `activation=not_needed` with the canonical validation route; do not run test-design tools or require `test_plan.md`.
1. Only for `activation=required`, record code paths and related test paths as survey and placement evidence, inspect branches/parsing/error/state transitions, and design a concrete behavior-regression oracle.
1. For `activation=required`, bind the owning design / contract clause to the reachable code-side implementation mechanism: public entrypoint, branches, parser and error paths, state transitions, and return projection. Do not infer the contract or oracle from tests alone.
1. Every nasty or regression case must carry one complete trace: `Design Clause -> Reachable Implementation Mechanism -> Concrete Breaking Input/State Sequence -> Observable Outcome -> Decidable Oracle`. A case is not test-design evidence until all five links are explicit.
1. Before implementation or handoff, state the contract-, type-, or checker-based null hypothesis that the candidate case cannot occur. Search for a reachability witness from the public input surface or a public state sequence; accept the case only when that witness rebuts the null hypothesis and supports a stable, decidable oracle. Without such a witness, return the candidate to the checker, static-validation, or owning-design boundary rather than turning it into a test.
1. `activation=required` does not mean exhaustive test generation. Choose one
   stable observation level per unresolved risk, reuse one case when it covers
   multiple risks, and omit duplicate contract checks, no-crash checks, and
   internal-shape checks already owned by static validation or existing tests.
1. For algorithm fixes, enter through the algorithm contract and code-side
   repair route before changing tests. Read the public entrypoint, recurrence or
   state transition, invariant, stopping or acceptance rule, failure semantics,
   and selected repair route from the owning algorithm skill or design packet.
   Treat related tests as symptom, regression-placement, and oracle-risk
   evidence until that route is fixed.
1. Before adding or recommending a test, decide whether the property is already owned by static analysis, a checker, formatter, dependency review, type checker, lint, docs check, or CI gate. For checker-owned properties, route the canonical command as validation evidence.
1. Classify validation findings by validation repair scope before applying an autofix. Findings tied to the changed contract, changed lines, or checker-owned property named in the task plan enter the current repair; broad pre-existing style debt becomes residual evidence with a separate repair route.
1. When a test or check fails during validation, do not immediately simplify, revert, delete features or tests, lower oracle strength, or remove intended behavior to make it pass. First identify the failing contract and observation level.
1. Record the validation-failure-response fields `failing_contract`, `observation_level`, `cause_classification`, `intent_preservation`, and `evidence`; use the slug sets and route semantics owned by `documents/runtime/runtime-profiles-and-check-matrix.json` for failure cause classification, approved intent preservation, and when to escalate before intent changes. Treat `documents/runtime/runtime-profiles-and-check-matrix.md` as the generated reader projection.
1. For `cause_classification=implementation_bug` with a stable contract, preserve approved intent and proceed to the owning code, config, docs, or workflow repair after classification; do not block that repair behind an extra test-design pass.
1. For algorithm bugs, update expected values, tolerances, and test oracle shape
   only after the algorithm contract and repair mechanism are fixed. Record
   why each test change follows the contract rather than the current failing
   output.
1. Before allowing behavior simplification, revert, intended-behavior removal, feature/test deletion, or oracle weakening, record a short failure-cause note in `test_plan.md`, work log, or review evidence.
1. For a `contract-only wrapper` or thin adapter, classify whether it adds observable behavior, branch logic, parser/error behavior, state mutation, diagnostic keys, serialization shape, or external process behavior. Names, types, forwards, configuration, and documentation for an existing contract use static contract validation and canonical command evidence.
1. Use API shape, helper identity, return shape, error prose, mock order or internal call sequence as test oracles only when the user request, approved design, documented external contract, or public behavior already fixes them. Otherwise record them under placement notes or `Do Not Freeze`.
1. For each required test case, fix `Contract Source`, `Behavior Contract`, `Observation Level`, `Observable Outcome`, `Oracle`, `Input Space`, `Adequacy Evidence`, and `Do Not Freeze`.
1. Classify generated execution-only placeholders such as `test_runs`, `test_smoke`, `test_generated_*`, or `test_can_run` as checker-command validation candidates when they observe only process success, import success, no-crash, or exit code 0.
1. Route mathematical judgments, oracles, and assertions through the `mathematical necessity gate`: connect them to `Numerical Trigger`, `Non-Numerical Alternative`, checker-owned property, proof obligation, or approved design acceptance criterion before making them test evidence.
1. Before proposing numerical, randomized, tolerance, solver, convergence,
   residual, benchmark, or experiment-style tests, apply the Numerical Test Admission Gate from `documents/conventions/coding-conventions-testing.md`: record the
   numerical trigger, non-numerical alternative, oracle, GPU target, and budget.
   If the target behavior is not numerical, omit the numerical test and record
   the omission reason instead. Do not propose CPU computational tests as a
   fallback for numerical validation.
1. Prefer behavior examples for concrete regressions, property tests for broad input spaces, metamorphic tests when exact expected output is hard, and mutation testing when oracle strength is doubtful.
1. Record nasty edge cases and regression cases in `test_plan.md` only when `activation=required`.
1. Keep cases concrete at the stable observation level: `Design Clause`, `Reachable Implementation Mechanism`, `Breaking Input/State Sequence`, `Observation Level`, `Observable Outcome`, `Decidable Oracle`, `Input Space`, `Adequacy Evidence`, `Do Not Freeze`, and why the case is nasty. Do not add tests merely to increase test count or coverage without this trace.
1. Mirror existing test style, fixture layout, and naming before suggesting anything new.
