# experiment-workflow

## Purpose

question、protocol、run、report を分けて実験を扱います。

## Use When

- benchmark
- method comparison
- 実験結果付きの改善

## Core References

- `documents/experiment-workflow.md`
- `documents/research-workflow.md`

## Boundary

- `experiment-lifecycle` は単一 run と rerun 分岐に寄せた Codex skill 名互換の入口です。
- 外側の反復設計は `research-workflow` を使います。
- 実験結果に応じて code change まで含めた自律 loop を回す場合は `experiment-change-loop` を追加します。
- methodology、artifact、reporting policy の大きい review は `research-perspective-review` を追加します。
