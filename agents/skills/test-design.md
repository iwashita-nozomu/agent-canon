# test-design
<!--
@dependency-start
contract skill
responsibility Documents test-design for this repository.
upstream design ../canonical/skills.md skill canon registry
@dependency-end
-->


## Reader Map

- Purpose: classifies oracle/spec risk and designs adversarial, resilient tests
  when changed behavior or regression risk needs explicit test evidence.
- Use When: implementation changes need static test design, oracle/spec-risk
  classification, nasty cases, regression cases, or brittle-test diagnosis.
- Section path: Purpose, Use When, and Core References orient scope; Expected
  Outcome, Mandatory Checklist, and Default Sequence are the operational rules;
  Common Failure Modes lists pitfalls.
- Boundary: this skill designs tests and validation evidence; it does not
  loosen behavior contracts to fit existing tests.

## Purpose

approved design と既存 code/test path を静的解析し、oracle / spec risk を分類し、必要な場合に変更耐性のある観測可能契約、stable observation level、oracle、input space、adequacy evidence を implementation 前に固定します。code path と test path は survey / placement evidence であり、未承認の API shape、private helper、private return shape、error prose、mock order、internal call sequence を作る根拠ではありません。`cause_classification=implementation_bug` で contract と oracle が安定している場合は、validation-failure-response fields を記録した後、追加の test-design pass で止めずに owning code / config / docs / workflow repair へ進めます。

## Use When

- behavior-changing、regression-prone、high-risk、または oracle / spec risk がある code を変える
- parser、validation、state transition、error handling を変える
- bug fix を durable test に変えたい
- 実装前に test 観点で穴を洗いたい
- validation failure の `cause_classification` が `test_oracle_spec_mismatch` か
  `implementation_bug` かを分類する必要がある

## Core References

- `agents/workflows/implementation-waterfall-workflow.md`
- `documents/coding-conventions-python.md`
- `documents/coding-conventions-testing.md`
- `references/test-design-flexibility.md`
- `documents/tools/test_design.md`
- `documents/REVIEW_PROCESS.md`
- `agents/templates/test_plan.md`

## Expected Outcome

- `test_plan.md` に static path survey、contract source、observation level、observable outcome、oracle、input space、adequacy evidence、nasty case、regression case、placement notes がある
- case が抽象論ではなく、contract source、入力、安定した観測結果、oracle まで具体化されている
- brittle coupling finding がある場合、残す理由または修正方針が書かれている
- 既存 test style、fixture、naming へどう寄せるかが書かれている
- static analysis、checker、formatter、dependency review、type checker、lint、
  docs check、CI gate が既に所有する性質は、validation route と evidence に
  戻されている
- contract-only wrapper では observable behavior trigger を先に判定し、
  static-only classification では static contract validation と canonical command
  evidence を validation route に置く
- validation repair scope が changed contract、changed lines、または task plan が名指しした
  checker-owned property に結び付いている
- validation 中に test / check が失敗した場合、`failing_contract`、
  `observation_level`、`cause_classification`、`intent_preservation`、
  `evidence`、または design / user-review escalation が
  `test_plan.md`、work log、review evidence のいずれかに短く書かれている
- 数値テストを提案する場合は numerical trigger、non-numerical alternative、oracle、
  budget があり、提案しない場合は省略理由と代替 observable behavior が書かれている
- 数理的な判定・oracle・assertion は `mathematical necessity gate` を通し、
  `Numerical Trigger`、`Non-Numerical Alternative`、checker-owned property、
  proof obligation、または approved design の acceptance criterion に接続している
- algorithm repair では、test plan が最初の修正面ではなく、algorithm contract、
  public entrypoint、recurrence / state transition、invariant、stopping /
  acceptance rule、failure semantics、code-side repair route の後に置かれている

## Mandatory Checklist

- changed code path と関連 test path を survey / placement evidence として記録している
- `tools/bin/agent-canon test-design check <related-test-paths...>` を先に走らせ、`fix-now` / `review` / `design-hint` を test plan に反映している
- `static-analysis-duplicate-test` と
  `meaningless-generated-execution-test` の `fix-now` finding を、deletion、
  behavior regression への置換、または canonical checker validation へ
  ルーティングしている
- `contract-only wrapper` は、入力 schema、型境界、設定 key、routing marker、
  dependency header、checker command の static contract validation へルーティングし、
  observable behavior が追加された場合だけ behavior example を候補にしている
- formatter、lint、checker が表出した既存 style debt や周辺 debt は residual evidence と
  repair route に分け、現在の diff を requested contract に沿った semantic change に保っている
- validation で test / check failure を見た後、すぐに単純化、revert、feature / test
  deletion、oracle strength の低下、intended behavior の削除へ進まず、`failing_contract`、
  `observation_level`、`cause_classification`、`intent_preservation`、`evidence` を
  記録している
- `cause_classification` と `intent_preservation` は
  `documents/runtime-profiles-and-check-matrix.md`、`agents/canonical/CODEX_WORKFLOW.md`、
  `agents/canonical/CODEX_SUBAGENTS.md`、`documents/REVIEW_PROCESS.md` の slug set と
  route semantics に従っている
- `cause_classification=implementation_bug` は approved intent を保ったまま owning
  code / config / docs / workflow repair へ進め、追加の test-design pass で
  implementation repair を止めない。必要な場合だけ同じ intent を保つ test を直すか追加する
- algorithm bug や solver bug では、関連 test は symptom / regression placement /
  oracle-risk evidence として扱い、先に algorithm contract と code-side repair route を
  固定する。test expectation、expected value、tolerance、oracle の変更は、その後で
  contract に合わせて判断する
- behavior simplification、revert、feature / test deletion、oracle weakening、
  intended behavior の削除を許す前に、短い failure-cause note を
  `test_plan.md`、work log、review evidence のいずれかに残している
- contract source、behavior contract、observation level、observable outcome、oracle、input space、adequacy evidence、do-not-freeze details を分けている
- 数値、randomized、tolerance、solver、convergence、residual、benchmark、
  experiment-style test を提案する前に `documents/coding-conventions-testing.md` の
  数値テスト採用ゲートを適用している
- malformed input、boundary value、empty / null-ish input、error path、state transition を列挙している
- 以前壊れたか、再発しやすい regression case を残している
- expected value、exception class/category、documented public response shape、public state mutation、diagnostic key、public failure mode のどれを固定するかを曖昧にしていない
- API shape、helper 名、private return shape、全文 error prose、mock order、internal call sequence は、user request / approved design / documented external contract / public behavior で固定済みの場合だけ oracle にしている
- parser / formatter / graph / router / mapping では property または metamorphic relation の候補を検討している
- assertion の強さが疑わしい場合は mutation testing または reviewer による oracle adequacy check を候補にしている
- 既存 test style を調べ、どの file / fixture / helper を再利用するか書いている

## Default Sequence

1. approved design と既存 code/test path を読み、code path と関連 test path を survey / placement evidence として記録します。target function / module / script は配置調査の根拠であり、未承認 API shape や internal call sequence を作る根拠ではありません。behavior-changing、regression-prone、high-risk、または oracle / spec risk がある場合に test design を深掘りします。
1. algorithm repair の場合は、`computational-optimization`、
   `algorithm-proof-exploration`、または該当する design owner が固定した
   algorithm contract、public entrypoint、recurrence / state transition、
   invariant、stopping / acceptance rule、failure semantics、code-side repair route
   を先に読む。関連 test はこの時点では survey / symptom / placement evidence です
1. 関連 test path がある場合は `tools/bin/agent-canon test-design check <paths...>` を実行します。新規 test の場合は `documents/coding-conventions-testing.md` を読み、同種の既存 test style を確認します。
1. `fix-now` finding は先に修正対象へ入れます。特に static-analysis duplicate や
   generated execution-only placeholder は、canonical checker validation へ戻すか、
   観測可能 behavior regression に置き換えます。
   `review` / `design-hint` は behavior contract と照合して残すか直すかを決めます。
1. validation tool の finding は validation repair scope に分類します。changed contract、
   changed lines、または task plan が名指しした checker-owned property に結び付くものを
   current repair に入れ、既存 style debt や周辺 debt は residual evidence に分けます。
1. validation 中に test / check が失敗した場合は、behavior を弱める前に
   `failing_contract`、`observation_level`、`cause_classification`、
   `intent_preservation`、`evidence` を記録します。slug set と route semantics は
   validation-failure-response owner surfaces を参照します。
1. `cause_classification=implementation_bug` は approved intent を保って owning
   code / config / docs / workflow repair へ進めます。必要な場合だけ同じ intent を保つ
   test を直すか追加し、generic `cause_classification=implementation_bug` を追加 test planning のために
   止めません。simplification、revert、deletion、oracle weakening の前に
   failure-cause note を `test_plan.md`、work log、review evidence のいずれかに残します。
1. contract-only wrapper では、observable behavior、branch、parser error path、
   state mutation、diagnostic key の trigger を先に判定します。static-only
   classification では static contract validation と canonical command evidence を
   test plan に置きます。
1. branch、error path、parsing path、state mutation point を静的に洗います。
1. 各 case の `Contract Source / Behavior Contract / Observation Level / Observable Outcome / Oracle / Input Space / Adequacy Evidence / Do Not Freeze` を固定します。
1. 数値テスト候補は `Numerical Trigger / Non-Numerical Alternative / Oracle / Budget` を固定し、trigger がない場合は省略理由と非数値の代替 test を書きます。
1. 数理的な判定・oracle・assertion は `mathematical necessity gate` の採用条件に照合し、checker-owned property や proof obligation で足りる性質を test oracle に昇格させる前に validation route へ戻します。
1. nasty case を `Contract Source / Observation Level / Case / Why It Is Nasty / Observable Outcome / Oracle` で列挙します。
1. regression として残すべき case を分けます。
1. worker がどこへ test を実装すべきかを `Implementation Notes` に書きます。

## Common Failure Modes

- happy path しか見ず、error path や malformed input が抜ける
- expected failure mode が曖昧で、test が assertion しにくい
- private helper、mock call sequence、stdout 全文、error prose 全文など、変更しやすい実装詳細を public contract と混同する
- tests が不要な API shape、private return shape、helper 名、error prose、mock order、internal call sequence を固定して harmless refactor を阻害する
- property / metamorphic relation が向いている変換系処理を、少数の example だけで固定する
- coverage だけを adequacy とみなし、assertion が mutant や regressions を捕まえるかを見ない
- 既存 test style を無視して別流儀の test を生やす
- bug fix を一回限りの手動確認で済ませて durable test に変えない
- static checker の成功を pytest で包んだだけの test を「coverage」として残す
- generated smoke / runs / no-crash test を、behavior contract と oracle なしで残す
- failing test / check を見た直後に、failing contract と cause classification を
  記録せず、simplification、revert、feature deletion、oracle weakening で pass だけを作る
- docs、routing、metadata、string parsing、configuration、structure refactor など
  数値契約を持たない変更に、数値 smoke、large random case、benchmark 風 test を生やす
