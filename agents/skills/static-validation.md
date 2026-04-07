# static-validation

## Purpose

変更内容に応じて最小限かつ十分な quality gate を選びます。

## Use When

- 何を検証すべきか決めたい
- docs / code / environment 変更の確認をそろえたい

## Standard Checks

- `make ci-quick`
- `make ci`
- `make docs-check`

## Boundary

- `static-check` は Codex skill 名互換の入口です。
- どの gate を組み合わせるかの正本はこの文書です。
