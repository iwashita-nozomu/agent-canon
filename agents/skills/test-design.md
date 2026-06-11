# test-design
<!--
@dependency-start
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

## Mandatory Checklist

- changed code path と関連 test path を固定している
- `tools/bin/agent-canon test-design check <related-test-paths...>` を先に走らせ、`fix-now` / `review` / `design-hint` を test plan に反映している
- behavior contract、observation level、oracle、input space、adequacy evidence を分けている
- malformed input、boundary value、empty / null-ish input、error path、state transition を列挙している
- 以前壊れたか、再発しやすい regression case を残している
- expected exception、error message、return shape、state mutation を曖昧にしていない
- parser / formatter / graph / router / mapping では property または metamorphic relation の候補を検討している
- assertion の強さが疑わしい場合は mutation testing または reviewer による oracle adequacy check を候補にしている
- 既存 test style を調べ、どの file / fixture / helper を再利用するか書いている

## Default Sequence

1. approved design と既存 code path を読み、target function / module / script を固定します。
1. 関連 test path がある場合は `tools/bin/agent-canon test-design check <paths...>` を実行します。新規 test の場合は `documents/coding-conventions-testing.md` を読み、同種の既存 test style を確認します。
1. `fix-now` finding は先に修正対象へ入れ、`review` / `design-hint` は behavior contract と照合して残すか直すかを決めます。
1. branch、error path、parsing path、state mutation point を静的に洗います。
1. 各 case の `Behavior Contract / Observation Level / Oracle / Input Space / Adequacy Evidence` を固定します。
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
