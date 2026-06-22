# test-design
<!--
@dependency-start
contract skill
responsibility Documents test-design for this repository.
upstream design ../canonical/skills.md skill canon registry
@dependency-end
-->


## Purpose

approved design と既存 code/test path を静的解析し、変更耐性のある behavior contract、oracle、input space、adequacy evidence を implementation 前に固定します。

## Use When

- code を変える
- parser、validation、state transition、error handling を変える
- bug fix を durable test に変えたい
- 実装前に test 観点で穴を洗いたい

## Core References

- `agents/workflows/implementation-waterfall-workflow.md`
- `documents/coding-conventions-python.md`
- `documents/coding-conventions-testing.md`
- `references/test-design-flexibility.md`
- `documents/tools/test_design.md`
- `documents/REVIEW_PROCESS.md`
- `agents/templates/test_plan.md`

## Expected Outcome

- `test_plan.md` に static path、behavior contract、oracle、input space、nasty case、regression case、implementation notes がある
- case が抽象論ではなく、target path、入力、期待結果まで具体化されている
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
- 数値テストを提案する場合は numerical trigger、non-numerical alternative、oracle、
  budget があり、提案しない場合は省略理由と代替 observable behavior が書かれている
- 数理的な判定・oracle・assertion は `mathematical necessity gate` を通し、
  `Numerical Trigger`、`Non-Numerical Alternative`、checker-owned property、
  proof obligation、または approved design の acceptance criterion に接続している

## Mandatory Checklist

- changed code path と関連 test path を固定している
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
- behavior contract、observation level、oracle、input space、adequacy evidence を分けている
- 数値、randomized、tolerance、solver、convergence、residual、benchmark、
  experiment-style test を提案する前に `documents/coding-conventions-testing.md` の
  数値テスト採用ゲートを適用している
- malformed input、boundary value、empty / null-ish input、error path、state transition を列挙している
- 以前壊れたか、再発しやすい regression case を残している
- expected exception、error message、return shape、state mutation を曖昧にしていない
- parser / formatter / graph / router / mapping では property または metamorphic relation の候補を検討している
- assertion の強さが疑わしい場合は mutation testing または reviewer による oracle adequacy check を候補にしている
- 既存 test style を調べ、どの file / fixture / helper を再利用するか書いている

## Default Sequence

1. approved design と既存 code path を読み、target function / module / script を固定します。
1. 関連 test path がある場合は `tools/bin/agent-canon test-design check <paths...>` を実行します。新規 test の場合は `documents/coding-conventions-testing.md` を読み、同種の既存 test style を確認します。
1. `fix-now` finding は先に修正対象へ入れます。特に static-analysis duplicate や
   generated execution-only placeholder は、canonical checker validation へ戻すか、
   観測可能 behavior regression に置き換えます。
   `review` / `design-hint` は behavior contract と照合して残すか直すかを決めます。
1. validation tool の finding は validation repair scope に分類します。changed contract、
   changed lines、または task plan が名指しした checker-owned property に結び付くものを
   current repair に入れ、既存 style debt や周辺 debt は residual evidence に分けます。
1. contract-only wrapper では、observable behavior、branch、parser error path、
   state mutation、diagnostic key の trigger を先に判定します。static-only
   classification では static contract validation と canonical command evidence を
   test plan に置きます。
1. branch、error path、parsing path、state mutation point を静的に洗います。
1. 各 case の `Behavior Contract / Observation Level / Oracle / Input Space / Adequacy Evidence` を固定します。
1. 数値テスト候補は `Numerical Trigger / Non-Numerical Alternative / Oracle / Budget` を固定し、trigger がない場合は省略理由と非数値の代替 test を書きます。
1. 数理的な判定・oracle・assertion は `mathematical necessity gate` の採用条件に照合し、checker-owned property や proof obligation で足りる性質を test oracle に昇格させる前に validation route へ戻します。
1. nasty case を `Target / Case / Why It Is Nasty / Expected Outcome / Oracle` で列挙します。
1. regression として残すべき case を分けます。
1. worker がどこへ test を実装すべきかを `Implementation Notes` に書きます。

## Common Failure Modes

- happy path しか見ず、error path や malformed input が抜ける
- expected failure mode が曖昧で、test が assertion しにくい
- private helper、mock call sequence、stdout 全文、error prose 全文など、変更しやすい実装詳細を public contract と混同する
- property / metamorphic relation が向いている変換系処理を、少数の example だけで固定する
- coverage だけを adequacy とみなし、assertion が mutant や regressions を捕まえるかを見ない
- 既存 test style を無視して別流儀の test を生やす
- bug fix を一回限りの手動確認で済ませて durable test に変えない
- static checker の成功を pytest で包んだだけの test を「coverage」として残す
- generated smoke / runs / no-crash test を、behavior contract と oracle なしで残す
- docs、routing、metadata、string parsing、configuration、structure refactor など
  数値契約を持たない変更に、数値 smoke、large random case、benchmark 風 test を生やす
