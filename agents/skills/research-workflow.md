# research-workflow

## Purpose

外部調査、比較設計、実装、run、critical review、report review を伴う研究系変更の outer loop を扱います。

## Use When

- 外部調査つき実装
- 性能改善や比較実験
- claim や method を更新する変更

## Core References

- `agents/skills/literature-survey.md`
- `documents/research-workflow.md`
- `documents/experiment-workflow.md`
- `documents/experiment-critical-review.md`

## Canonical Loop

1. 問い、比較対象、exit criteria を固定する
1. `literature-survey` を使って外部調査を行い、採用候補と反証候補を残す
1. 比較プロトコルと run layout を固定する
1. baseline または current state を記録する
1. 1 つの code change を入れる
1. 同じ protocol で run する
1. `critical-review` と `report-review` を通す
1. `report_rewrite_required`、`extra_validation_required`、`rerun_required`、`approved` の decision に応じて loop を戻す

## Boundary

- 単一 run の設計と出力整理は `experiment-workflow` を使います。
- 実験結果を見ながら code change を継続反復する場合は `experiment-change-loop` を追加します。
- 文献探索そのものは `literature-survey` を使います。
- 大きい methodology / artifact / reporting policy 変更の独立レビューは `research-perspective-review` を使います。
