# md-style-check

<!--
@dependency-start
contract skill
responsibility Documents md-style-check for this repository.
upstream design ../canonical/skills.md skill canon registry
@dependency-end
-->

## Reader Map

- Purpose: keeps Markdown style, headings, links, math, Mermaid, and formatter
  output aligned with repository documentation rules.
- Use When: editing Markdown, fixing docs-check findings, running docs format,
  or validating link, heading, math, or Mermaid drift.
- Section path: Purpose, Use When, Required Checks, and Core References orient
  the route; Expected Outcome, Mandatory Checklist, Default Sequence, Boundary,
  and Final Guard are the operational rules.
- Boundary: substantive document structure or responsibility changes require
  structure-planning and prose-reasoning before this style gate.

## Purpose

Markdown の体裁、見出し、リンク、可読性を崩さずに保ちます。
formatter を実行した場合は、体裁修正だけで完了にせず、同じ入口で周辺チェックまで閉じます。
この skill 単独で扱うのは typo / link / format-only の文書変更です。
repo-changing task 全体が owner-bounded 修正として閉じる場合は `$owner-bounded-routing`
と組み合わせ、owner boundary、existing-tool route、targeted validation を残します。
section order、reader path、claim support、source map、canonical route、
document responsibility が変わる substantive な文書変更では、
`prose-reasoning-graph` と `structure-planning` を先に通し、
format-only route では `structure_contract=skipped` と理由を evidence に残します。

## Use When

- `.md` を触る
- 文書整理や report 整備を行う
- user request が plain `md-style-check` または `$md-style-check` を挙げている
- docs lint、link check、heading hierarchy、markdown math、docs-check failure、Markdown style drift を直す
- docs formatter、Mermaid formatter、math fixer、または `agent-canon docs` が scope にある
- formatter 後の lint、link、math、Mermaid、heading の確認が抜けている
- substantive な文書変更は `prose-reasoning-graph` と `structure-planning` の構造解析後に、この skill で Markdown checks を閉じる

## Required Checks

- `tools/bin/agent-canon docs check <paths...>`
- `tools/bin/agent-canon docs format <paths...>` when formatter repair is needed
- `tools/bin/agent-canon docs fix-math <paths...>` when math delimiter repair is needed
- `tools/bin/agent-canon docs fix-mermaid <paths...>` when Mermaid repair is needed

## Core References

- `documents/coding-conventions-project.md`
- `documents/conventions/common/05_docs.md`
- `.markdownlint.json`
- `rust/agent-canon/src/docs.rs`

## Expected Outcome

- Markdown の体裁、見出し階層、リンクが repo ルールに揃っている
- broken link や heading drift が未解決のまま残っていない
- 体裁の問題と中身の問題が分けて整理されている
- formatter を走らせた差分では、隣接する Markdown lint、link、math、Mermaid、heading checks が同じ evidence に残っている

## Mandatory Checklist

- typo / link / format-only route では、runtime `SKILL.md` 読了を docs tool 実行や patching の前提にしない
- owner boundary、existing-tool route、targeted validation が evidence に残っている
- changed Markdown files have been checked with `tools/bin/agent-canon docs check`
- 見出し階層が飛んでいない
- command、path、file reference の書式が揃っている
- 絶対パスリンクや repo 内リンクが壊れていない
- list、table、code block が読みにくく崩れていない
- display math は standalone double-dollar delimiter を使い、KaTeX / math
  fence と Markdown display delimiter を二重に重ねていない
- 文中数式 / inline math は `$...$`（例: `$(式)$`）で囲み、backtick の
  code span や文中の double-dollar display delimiter にしていない
- formatter 後に escaped display delimiter や余分な double-dollar delimiter が残っていない
- table 内の文中数式や inline code が raw `|` で列分割されていない
- Mermaid fenced block と math delimiter が repo 標準に揃っている
- 体裁修正の結果、意味や正本リンクを壊していない
- formatter / fixer 実行後に `tools/bin/agent-canon docs check <paths...>` を通している

## Default Sequence

1. changed Markdown files を固定します。
1. display math がある file は、double-dollar delimiter を独立行に置き、前後に空行を置きます。KaTeX / math fence の中に Markdown display delimiter を入れません。
1. 文中数式 / inline math は `$...$`（例: `$(式)$`）で書き、code span や文中の double-dollar display delimiter と混ぜません。
1. command option や実行例が必要な場合は、実装 file を読む前に `tools/bin/agent-canon docs -h` を見ます。
1. 文書全体を読む前に `tools/bin/agent-canon docs check <paths...>` を実行し、lint、link、math、Mermaid、heading を同時に見ます。`DOCS_CHECK=pass`、`DOCS_CHECK_FINDING=...`、`DOCS_CHECK_REPORT_BEGIN` の structured report は tool-covered property の正本判定として扱います。
1. finding がある場合だけ、修正に必要な path / line / 近傍 slice を読みます。tool が見た property を subagent や reviewer に再読解させません。
1. formatting drift がある場合は `tools/bin/agent-canon docs format <paths...>` を使い、その command が続けて走らせる adjacent check の結果まで確認します。
1. markdown math drift は `tools/bin/agent-canon docs fix-math <paths...>`、Mermaid drift は `tools/bin/agent-canon docs fix-mermaid <paths...>` で機械修正し、修正後の check 結果を evidence に残します。
1. formatter や fixer が display delimiter を escape したり、余分な double-dollar delimiter を作ったりした場合は、display math の block 形を直してから `tools/bin/agent-canon docs check <paths...>` を再実行します。
1. 体裁違反、broken link、見出し drift を修正します。
1. 文書間の矛盾や内容不足が見えたら、それぞれ docs consistency review、docs completeness review へ分岐します。

## Boundary

- 文書内容の不足確認は docs completeness review を使います。
- 文書間の矛盾や stale route は docs consistency review を使います。

## Final Guard

- formatter と checker が pass しても、最後に変更箇所の table、文中数式、
  inline code を確認します。文中数式は `$...$`、code/path/literal は backtick
  で分けます。table cell の中に raw `|` を含む数式や code を置くと
  Markdown の列として解釈されるため、式を display math へ出す、短い名前へ置換する、
  または table 外の本文へ移してから、`tools/bin/agent-canon docs check <paths...>` を再実行します。
- format-only として閉じる場合は、`structure_contract=skipped` と理由が
  run bundle、work log、PR body、または closeout evidence に残っていることを確認します。
- docs formatter / fixer / checker failure を修復へ回す場合は、
   validation-failure-response packet の `failing_contract`、`observation_level`、
   `cause_classification`、`intent_preservation`、`evidence` を記録します。
   `intent_preservation` は same-intent repair / owner-route repair / residual
   classification / escalation route を示します。pass 目的の scope 縮小、
   link / heading oracle weakening、または validation downscope で閉じてはいけません。
