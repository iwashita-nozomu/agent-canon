# test-design
<!--
@dependency-start
@dependency-end
-->


## Purpose

approved design と既存 code path を静的解析し、最も意地の悪い edge case、failure path、regression case を implementation 前に固定します。

## Use When

- code を変える
- parser、validation、state transition、error handling を変える
- bug fix を durable test に変えたい
- 実装前に test 観点で穴を洗いたい

## Core References

- `agents/workflows/implementation-waterfall-workflow.md`
- `documents/coding-conventions-python.md`
- `documents/REVIEW_PROCESS.md`
- `agents/templates/test_plan.md`

## Expected Outcome

- `test_plan.md` に static path、nasty case、regression case、implementation notes がある
- case が抽象論ではなく、target path、入力、期待結果まで具体化されている
- 既存 test style、fixture、naming へどう寄せるかが書かれている

## Mandatory Checklist

- changed code path と関連 test path を固定している
- malformed input、boundary value、empty / null-ish input、error path、state transition を列挙している
- 以前壊れたか、再発しやすい regression case を残している
- expected exception、error message、return shape、state mutation を曖昧にしていない
- 既存 test style を調べ、どの file / fixture / helper を再利用するか書いている

## Default Sequence

1. approved design と既存 code path を読み、target function / module / script を固定します。
1. branch、error path、parsing path、state mutation point を静的に洗います。
1. nasty case を `Target / Case / Why It Is Nasty / Expected Outcome` で列挙します。
1. regression として残すべき case を分けます。
1. worker がどこへ test を実装すべきかを `Implementation Notes` に書きます。

## Common Failure Modes

- happy path しか見ず、error path や malformed input が抜ける
- expected failure mode が曖昧で、test が assertion しにくい
- 既存 test style を無視して別流儀の test を生やす
- bug fix を一回限りの手動確認で済ませて durable test に変えない
