# experiment-change-loop

## Purpose

実験結果を根拠に 1 change ずつ改造し、review で `approved` になるまで loop を自律的に回すための運用を定めます。

## Use When

- benchmark や性能改善を根拠に code を段階的に改造する
- 同じ protocol で baseline と change を繰り返し比較する
- agent に `implement -> run -> review -> decide` を継続させたい
- 実験結果付きの改造を、思いつきではなく明示的な decision state で閉じたい

## Core References

- `agents/skills/experiment-workflow.md`
- `agents/skills/research-workflow.md`
- `agents/skills/critical-review.md`
- `agents/skills/report-review.md`
- `documents/experiment-workflow.md`
- `documents/research-workflow.md`
- `agents/templates/experiment_change_loop.md`

## Inputs

- `Question:`
- `Comparison Target:`
- `Exit Criteria:`
- baseline または current state
- 固定した protocol と fairness rule
- write scope

## Outputs

- loop log
- iteration ごとの decision state
- 次に入れる 1 change
- close 可能かどうかの判断

## Canonical Loop

1. `Question:`、`Comparison Target:`、`Exit Criteria:` を固定する
1. baseline または current state を同じ protocol で記録する
1. 今回入れる change を 1 つだけ選ぶ
1. 実装と静的チェックを行う
1. 同じ protocol で fresh run を行う
1. `Quantitative Summary:` と report draft を更新する
1. `critical-review` と `report-review` を通す
1. decision に応じて loop を戻す

## Decision States

- `report_rewrite_required`
  - 同じ result を使い、report だけを書き直します。
- `extra_validation_required`
  - 同じ仮説のまま追加 case、追加 figure、追加集計を行います。
- `rerun_required`
  - code か protocol を修正し、新しい `run_name` で fresh rerun します。
- `approved`
  - exit criteria を満たしていれば loop を閉じます。満たしていなければ次の 1 change を設計します。

## Operating Rules

- 1 iteration で code change は 1 つだけにします。
- baseline と change の比較条件を途中でずらしません。
- `report_rewrite_required`、`extra_validation_required`、`rerun_required` が残る限り loop を閉じません。
- 2 つ目の change を入れる前に、前の iteration の decision state を確定させます。
- `approved` の前に、最新 run、critical review、report review の対応を記録します。

## Required Records

- `Question:`
- `Comparison Target:`
- `Exit Criteria:`
- `Iteration Goal:`
- `Change:`
- `Expected Effect:`
- `Validation Plan:`
- `Run Name / Path:`
- `Critical Review:`
- `Report Review:`
- `Decision:`
- `Next Action:`

## Suggested Templates

- `agents/templates/experiment_change_loop.md`
- `agents/templates/experiment_log.md`
- `agents/templates/decision_log.md`

## Boundary

- 外部調査そのものは `literature-survey` を使います。
- 単一 run の設計と出力整理は `experiment-workflow` を使います。
- 研究系変更の outer loop は `research-workflow` を使います。
- methodology、artifact、reporting policy を大きく変える場合は `research-perspective-review` を追加します。
- run のために Docker、dependency、CI を触る場合は `environment-maintenance` を併用します。
