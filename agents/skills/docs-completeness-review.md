# docs-completeness-review

## Purpose

文書が存在するだけでなく、読者が作業や判断に必要な情報を欠かさず持っているかをレビューします。

## Use When

- README、設計文書、workflow 文書の不足確認
- 入口、前提、手順、出力先、禁止事項の欠落確認
- 実装変更後に docs が追随しているかの確認

## Core References

- `documents/coding-conventions-project.md`
- `documents/README.md`
- `agents/skills/docs-consistency-review.md`
- `agents/skills/md-style-check.md`

## Expected Outcome

- 読者が次に何をするか迷わない文書になっている
- 欠けている前提、入力、出力、コマンド、判断基準が明示される
- 書式の問題ではなく、中身の欠落が findings として分かる

## Mandatory Checklist

- 文書だけで対象、目的、入口が分かる
- 手順文書なら入力、出力、主要コマンドがある
- 規約文書なら禁止、必須、許可、任意が明示されている
- 実験文書なら run path と report path がある
- review や workflow 文書なら decision point と closeout 条件がある
- 環境文書なら prerequisites、validation、rollback がある

## Default Sequence

1. 読者を 1 人決めます。新規参加者、実装者、reviewer、運用者のどれかに固定します。
1. その読者が最初の 5 分で必要な情報が全部あるかを見ます。
1. 入口、前提、手順、出力先、禁止事項、完了条件の順に不足を探します。
1. 欠落は wording ではなく information gap として findings 化します。
1. 文書間矛盾が見えたら `docs-consistency-review` へ回します。

## Boundary

- Markdown の体裁だけを見るなら `md-style-check` を使います。
- 文書間の矛盾や stale route を潰すなら `docs-consistency-review` を使います。
