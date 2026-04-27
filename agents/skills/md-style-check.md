# md-style-check
<!--
@dependency-start
upstream design ../canonical/skills.md skill canon registry
@dependency-end
-->


## Purpose

Markdown の体裁、見出し、リンク、可読性を崩さずに保ちます。

## Use When

- `.md` を触る
- 文書整理や report 整備を行う

## Required Checks

- `make docs-check`

## Core References

- `documents/conventions/common/05_docs.md`
- `.markdownlint.json`

## Expected Outcome

- Markdown の体裁、見出し階層、リンクが repo ルールに揃っている
- broken link や heading drift が未解決のまま残っていない
- 体裁の問題と中身の問題が分けて整理されている

## Mandatory Checklist

- 見出し階層が飛んでいない
- command、path、file reference の書式が揃っている
- 絶対パスリンクや repo 内リンクが壊れていない
- list、table、code block が読みにくく崩れていない
- 体裁修正の結果、意味や正本リンクを壊していない

## Default Sequence

1. changed Markdown files を固定します。
1. `make docs-check` を実行し、lint と link の両方を見ます。
1. 体裁違反、broken link、見出し drift を修正します。
1. 文書間の矛盾や内容不足が見えたら、それぞれ docs consistency review、docs completeness review へ分岐します。

## Boundary

- 文書内容の不足確認は docs completeness review を使います。
- 文書間の矛盾や stale route は docs consistency review を使います。
