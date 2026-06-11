# md-style-check

<!--
@dependency-start
responsibility Documents md-style-check for this repository.
upstream design ../canonical/skills.md skill canon registry
@dependency-end
-->

## Purpose

Markdown の体裁、見出し、リンク、可読性を崩さずに保ちます。

## Use When

- `.md` を触る
- 文書整理や report 整備を行う
- user request が plain `md-style-check` または `$md-style-check` を挙げている
- docs lint、link check、heading hierarchy、markdown math、docs-check failure、Markdown style drift を直す

## Required Checks

- `python3 tools/docs/format_markdown.py <changed Markdown files>`
- `mdformat <changed Markdown files>`
- `mdformat --check <changed Markdown files>`
- `python3 tools/docs/check_markdown_math.py <changed Markdown files>` when
  display math is present or math delimiters changed
- `make docs-check`

## Core References

- `documents/coding-conventions-project.md`
- `documents/conventions/common/05_docs.md`
- `.markdownlint.json`

## Expected Outcome

- Markdown の体裁、見出し階層、リンクが repo ルールに揃っている
- broken link や heading drift が未解決のまま残っていない
- 体裁の問題と中身の問題が分けて整理されている

## Mandatory Checklist

- changed Markdown files have been passed through `mdformat`
- 見出し階層が飛んでいない
- command、path、file reference の書式が揃っている
- 絶対パスリンクや repo 内リンクが壊れていない
- list、table、code block が読みにくく崩れていない
- display math は standalone double-dollar delimiter を使い、KaTeX / math
  fence と Markdown display delimiter を二重に重ねていない
- `mdformat` 後に escaped display delimiter や余分な double-dollar delimiter が残っていない
- table 内の文中数式や inline code が raw `|` で列分割されていない
- 体裁修正の結果、意味や正本リンクを壊していない

## Default Sequence

1. changed Markdown files を固定します。
1. display math がある file は、double-dollar delimiter を独立行に置き、前後に空行を置きます。KaTeX / math fence の中に Markdown display delimiter を入れません。
1. repo 固有 formatter の `python3 tools/docs/format_markdown.py <paths>` を実行します。
1. `mdformat <paths>` を実行します。
1. `mdformat --check <paths>` を実行し、formatter drift が残っていないことを確認します。
1. markdown math drift がある場合、または display math delimiter を含む file を触った場合は `python3 tools/docs/check_markdown_math.py <paths>` で確認し、delimiter だけの機械修正は `python3 tools/docs/fix_markdown_math.py <paths>` を使います。
1. `mdformat` が display delimiter を escape したり、余分な double-dollar delimiter を作ったりした場合は、display math の block 形を直してから `mdformat` と math check を再実行します。
1. `make docs-check` を実行し、lint と link の両方を見ます。
1. 体裁違反、broken link、見出し drift を修正します。
1. 文書間の矛盾や内容不足が見えたら、それぞれ docs consistency review、docs completeness review へ分岐します。

## Boundary

- 文書内容の不足確認は docs completeness review を使います。
- 文書間の矛盾や stale route は docs consistency review を使います。

## Final Guard

- formatter と checker が pass しても、最後に変更箇所の table、文中数式、
  inline code を確認します。table cell の中に raw `|` を含む数式や code を置くと
  Markdown の列として解釈されるため、式を display math へ出す、短い名前へ置換する、
  または table 外の本文へ移してから、`format_markdown.py`、`mdformat`、
  `mdformat --check`、`check_markdown_math.py` を再実行します。
