# Mathematical Formulation

## Purpose

問題設定、記号、目的関数、制約、比較境界を固定し、実装前の canonical formulation を明文化します。

## Use This For

- exact line と relaxed line を混ぜずに整理したいとき
- objective、constraint、state、parameter、solver boundary を固定したいとき
- 数理主張と implementation plan を切り分けたいとき
- 文献調査のあとに canonical な問いと非ゴールを確定したいとき

## Quick Path

1. `framework-inventory` で reuse surface と禁止する重複実装を固定する
1. `Question`、成功条件、非ゴールを 1 段落で固定する
1. notation ledger を作り、変数、shape、domain、index range を並べる
1. objective、constraint、state transition、solver subproblem を分離して書く
1. exact / relaxed / heuristic を分け、baseline との差分を formulation 上で説明する
1. 実装へ渡す前に `mathematical-validity-review` を通す

## Canonical Output Shape

- `Question`
  - 何を解き、何を比較し、何を主張しないか
- `Notation ledger`
  - 記号、shape、空間、添字の定義
- `Objective and constraints`
  - 目的関数と制約
- `State transition or solver subproblem`
  - 更新則、部分問題、停止条件
- `Exact / relaxed / heuristic boundary`
  - どこまでが exact claim で、どこから近似か
- `Implementation preconditions`
  - API boundary、data boundary、solver boundary
- `Open assumptions and failure cases`
  - まだ証明していない点、壊れやすい条件

## Must Read Before Working

- `agents/skills/framework-inventory.md`
- 必要なら `agents/skills/literature-survey.md`
- 対象 topic の `documents/design/` 正本
- 対象 topic の `notes/themes/` と `references/`

## Inputs

- research question
- baseline and comparison targets
- candidate notation
- 関連文献と既存 design doc

## Outputs

- canonical formulation
- assumption ledger
- exact / relaxed / heuristic boundary
- implementation に渡す design preconditions

## Mandatory Checklist

- `Question`、成功条件、非ゴールを先に固定する
- 変数、空間、添字、shape、記号の意味を固定する
- objective、constraint、state update、solver subproblem を分けて書く
- exact claim、relaxation、近似、heuristic を明示的に分ける
- baseline と comparison target を formulation 上の違いとして説明する
- 実装で必要な API boundary、data boundary、solver boundary を明記する
- failure case、open assumption、未証明点を隠さず列挙する

## Standard Flow

1. `framework-inventory` の結果から reuse できる surface と禁止する重複実装を固定する
1. 問い、評価指標、comparison target を 1 段落で固定する
1. canonical notation と variable ledger を作る
1. objective、constraint、state transition、solver subproblem を分離して書く
1. exact / relaxed / heuristic の境界を明記する
1. 実装に渡す前に `mathematical-validity-review` を通す

## Boundary

- 文献探索の広い survey は `agents/skills/literature-survey.md` を使います。
- 数理の独立レビューは `agents/skills/mathematical-validity-review.md` を使います。
- diff や API の設計レビューは `agents/skills/change-review.md` を使います。

## Implementation Surface

- shared canon only
