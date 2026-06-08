# md-style-check
<!--
@dependency-start
responsibility Documents md-style-check for this repository.
upstream design ../canonical/skills.md skill canon registry
@dependency-end
-->


## Purpose

Markdown の体裁、見出し、リンク、可読性を崩さずに保ちます。
formatter を実行した場合は、体裁修正だけで完了にせず、同じ入口で周辺チェックまで閉じます。

## Use When

- `.md` を触る
- 文書整理や report 整備を行う
- user request が plain `md-style-check` または `$md-style-check` を挙げている
- docs lint、link check、heading hierarchy、markdown math、docs-check failure、Markdown style drift を直す
- `format_markdown.py`、docs formatter、Mermaid formatter、math fixer、または `agent-canon docs` が scope にある
- formatter 後の lint、link、math、Mermaid、heading の確認が抜けている

## Required Checks

- `tools/bin/agent-canon docs check <paths...>`

## Core References

- `documents/conventions/common/05_docs.md`
- `.markdownlint.json`
- `rust/agent-canon/src/docs.rs`

## Expected Outcome

- Markdown の体裁、見出し階層、リンクが repo ルールに揃っている
- broken link や heading drift が未解決のまま残っていない
- 体裁の問題と中身の問題が分けて整理されている
- formatter を走らせた差分では、隣接する Markdown lint、link、math、Mermaid、heading checks が同じ evidence に残っている

## Mandatory Checklist

- 見出し階層が飛んでいない
- command、path、file reference の書式が揃っている
- 絶対パスリンクや repo 内リンクが壊れていない
- list、table、code block が読みにくく崩れていない
- Mermaid fenced block と math delimiter が repo 標準に揃っている
- 体裁修正の結果、意味や正本リンクを壊していない
- formatter / fixer 実行後に `tools/bin/agent-canon docs check <paths...>` を通している

## Default Sequence

1. changed Markdown files を固定します。
1. 文書全体を読む前に `tools/bin/agent-canon docs check <paths...>` を実行し、lint、link、math、Mermaid、heading を同時に見ます。`DOCS_CHECK=pass` と `DOCS_CHECK_FINDING=...` は tool-covered property の正本判定として扱います。
1. finding がある場合だけ、修正に必要な path / line / 近傍 slice を読みます。tool が見た property を subagent や reviewer に再読解させません。
1. formatting drift がある場合は `tools/bin/agent-canon docs format <paths...>` を使い、その command が続けて走らせる adjacent check の結果まで確認します。
1. markdown math drift は `tools/bin/agent-canon docs fix-math <paths...>`、Mermaid drift は `tools/bin/agent-canon docs fix-mermaid <paths...>` で機械修正し、修正後の check 結果を evidence に残します。
1. 体裁違反、broken link、見出し drift を修正します。
1. 文書間の矛盾や内容不足が見えたら、それぞれ docs consistency review、docs completeness review へ分岐します。

## Boundary

- 文書内容の不足確認は docs completeness review を使います。
- 文書間の矛盾や stale route は docs consistency review を使います。
