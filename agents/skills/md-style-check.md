# md-style-check

<!--
@dependency-start
contract skill
responsibility Documents md-style-check for this repository.
upstream design ../canonical/skills.md skill canon registry
upstream design ../../ROOT_AGENTS.md shared post-edit formatting boundary
upstream design code-visualization.md sole public visualization owner and typed projection contract
upstream design report-writing.md report evidence and optional structure boundary
upstream design structure-planning.md actual structural decision owner
upstream design ../../documents/runtime/runtime-profiles-and-check-matrix.md responsibility-owned validation selection
downstream implementation ../../tests/tools/test_fix_mermaid.py tests formatter and post-format coverage behavior
@dependency-end
-->

## Visualization Formatter Gate

For Mermaid artifacts, `md-style-check` is a formatter/checker adapter to
[`code-visualization`](code-visualization.md). It receives the owner's `VisualizationSourceUniverse`,
canonical `ToolCall`, and `ProjectionCoverageManifest`, formats the complete
artifact, and returns post-format readback identities for the owner's final
coverage status. Formatting owns syntax only: it cannot repair an omission by
rewriting, aggregating, substituting, or deleting content, and a pre-format
marker is not readback evidence.

## Reader Map

- Purpose: keeps Markdown style, headings, links, math, Mermaid, and formatter
  output aligned with repository documentation rules.
- Use When: editing Markdown, fixing docs-check findings, running docs format,
  or validating link, heading, math, or Mermaid drift.
- Section path: Purpose, Use When, Required Checks, and Core References orient
  the route; Expected Outcome, Mandatory Checklist, Default Sequence, Boundary,
  and Final Guard are the operational rules.
- Boundary: use the changed document's owner for meaning and evidence;
  [Purpose](#purpose) defines when structural work is relevant.

## Purpose

Markdown の体裁、見出し、リンク、可読性を崩さずに保ちます。
編集後の整形は [ROOT_AGENTS.md の Validation Routing](../../ROOT_AGENTS.md#validation-routing)
に従い、整形した最終差分に対して必要な検証まで閉じます。
formatter を実行した場合は、体裁修正だけで完了にせず、同じ入口で周辺チェックまで閉じます。
この skill 単独で扱うのは typo / link / format-only の文書変更です。
repo-changing task 全体が bounded owner 修正として閉じる場合は通常の owner route
と組み合わせ、owner boundary、existing-tool route、targeted validation を残します。
文書の意味と根拠は変更 owner が確認し、Markdown の変更だけを理由に構造解析を
前置しません。見出し配置、reader path、責務分割など実際の構造設計が必要な場合だけ
[structure-planning](structure-planning.md) の適用条件に従います。
報告は [report-writing](report-writing.md) に従い、主張・根拠・結論の修正だけで
prose graph や構造計画を要求しません。未選択の構造解析に skip 記録は不要です。

## Use When

- `.md` の変更を、その repository の文書 owner が定める方法で検証する
- 文書整理や report 整備を行う
- user request が plain `md-style-check` または `$md-style-check` を挙げている
- docs lint、link check、heading hierarchy、markdown math、docs-check failure、Markdown style drift を直す
- docs formatter、Mermaid formatter、math fixer、または `agent-canon docs` が scope にある
- formatter 後の lint、link、math、Mermaid、heading の確認が抜けている

## Required Checks

Select checks from the changed repository's documentation owner and
[validation matrix](../../documents/runtime/runtime-profiles-and-check-matrix.md).
Project-owned documentation uses its project-owned validation directly, not as
a fallback after trying AgentCanon. A Markdown edit or this skill's selection
alone does not require an AgentCanon checker. Do not probe, install, register,
or repair an unselected AgentCanon checker, or record its omission as skipped
or as a verification gap. If no automated check is prescribed, review the changed
document against the owner's contract. A genuinely required check that fails
or is unavailable remains unresolved; another check's pass does not replace it.

The following command examples apply only when AgentCanon source validation
or the project documentation owner explicitly selects the AgentCanon tool:

- `tools/bin/agent-canon docs check <paths...>`
- `tools/bin/agent-canon docs format <paths...>` when formatter repair is needed
- `tools/bin/agent-canon docs fix-math <paths...>` when math delimiter repair is needed
- `tools/bin/agent-canon docs fix-mermaid <paths...>` when Mermaid repair is needed

## Core References

- [`coding-conventions-project.md`](../../documents/conventions/coding-conventions-project.md)
- [`05_docs.md`](../../documents/conventions/common/05_docs.md)
- `.markdownlint.json`
- `tools/runtime/dispatch/agent-canon/src/docs.rs`

## Link Convention

文書または skill の reader-facing な参照は、[`05_docs.md`](../../documents/conventions/common/05_docs.md)
の標準相対 Markdown リンク規約に従います。この skill はそのリンクの存在と相対 path の
整合を確認します。command、glob、placeholder、machine-readable header / directive、literal
output、および `$skill-name` の invocation syntax は code のままにします。reader-facing な
skill owner は canonical doc（例えば [`md-style-check`](md-style-check.md)）へリンクし、公開
skill の identity と relation は [`catalog.yaml`](catalog.yaml) を machine-readable な正本として
扱います。

## Expected Outcome

- Markdown の体裁、見出し階層、リンクが repo ルールに揃っている
- broken link や heading drift が未解決のまま残っていない
- 体裁の問題と中身の問題が分けて整理されている
- formatter を走らせた差分では、隣接する Markdown lint、link、math、Mermaid、heading checks が同じ evidence に残っている

## Mandatory Checklist

- typo / link / format-only route では、runtime `SKILL.md` 読了を docs tool 実行や patching の前提にしない
- owner boundary、existing-tool route、targeted validation が evidence に残っている
- changed Markdown files have been validated through the documentation owner's selected route
- 見出し階層が飛んでいない
- command、path、file reference の書式が揃っている
- 絶対パスリンクや repo 内リンクが壊れていない
- list、table、code block が読みにくく崩れていない
- display math は standalone double-dollar delimiter を使い、KaTeX / math
  fence と Markdown display delimiter を二重に重ねていない
- 文中数式 / inline math は `$...$`（例: `$(式)$`）で囲み、backtick の
  code span や文中の double-dollar display delimiter にしていない
- `text` / `plaintext` / `txt` / `plain` 指定の fenced block には数式を
  入れず、`math` / `latex` / `tex` 指定の fenced block も使わない。これらの
  fence info の先頭 token は大文字小文字を区別せずに判定される。数式は本文中
  `$...$` または standalone double-dollar block のみを使う
- formatter 後に escaped display delimiter や余分な double-dollar delimiter が残っていない
- table 内の文中数式や inline code が raw `|` で列分割されていない
- Mermaid fenced block と math delimiter が repo 標準に揃っている
- 体裁修正の結果、意味や正本リンクを壊していない
- formatter / fixer 実行後も、同じ owner が選択した必要な検査で変更を確認している

## Default Sequence

1. changed Markdown files と、その文書 owner の検査・修正経路を [Required Checks](#required-checks) に従って固定します。
1. display math がある file は、double-dollar delimiter を独立行に置き、前後に空行を置きます。KaTeX / math fence の中に Markdown display delimiter を入れません。
1. 文中数式 / inline math は `$...$`（例: `$(式)$`）で書き、code span や文中の double-dollar display delimiter と混ぜません。
1. 数式を `text` / `plaintext` / `txt` / `plain` の fenced block に入れず、
   `math` / `latex` / `tex` の fenced block も使わず、`$...$` か standalone
   double-dollar block へ正規化します。info token の大文字小文字は問いません。
1. command option や実行例が必要な場合は、選択済み tool の help を見ます。
1. 自動検査が選択されている場合は実行し、その report を検査対象 property の判定根拠にします。検査対象外の性質まで pass と扱いません。
1. finding がある場合だけ、修正に必要な path / line / 近傍 slice を読みます。tool が見た property を subagent や reviewer に再読解させません。
1. formatting、math、Mermaid の drift は owner の選択済み formatter / fixer があれば利用して修正し、同じ owner の必要な検査で修正後を確認します。command がその検査を既に実行した場合は結果を再利用し、重ねて起動しません。
1. formatter や fixer が display delimiter を escape したり、余分な double-dollar delimiter を作ったりした場合は、display math の block 形を直してから選択済みの検査を再実行します。
1. 体裁違反、broken link、見出し drift を修正します。
1. 文書間の矛盾や内容不足が見えたら、それぞれ docs consistency review、docs completeness review へ分岐します。

## Boundary

- 文書内容の不足確認は docs completeness review を使います。
- 文書間の矛盾や stale route は docs consistency review を使います。

## Final Guard

この確認で再編集した場合は、[Default Sequence](#default-sequence) の最終整形からやり直します。

- formatter と checker が pass しても、最後に変更箇所の table、文中数式、
  inline code を確認します。文中数式は `$...$`、literal な code/path/value は backtick
  で分け、reader-facing な文書・skill 参照は [`05_docs.md`](../../documents/conventions/common/05_docs.md) の標準相対 Markdown link
  にします。table cell の中に raw `|` を含む数式や code を置くと
  Markdown の列として解釈されるため、式を display math へ出す、短い名前へ置換する、
  または table 外の本文へ移してから、選択済みの文書検査で変更を確認します。
- docs formatter / fixer / checker failure を修復へ回す場合は、
   validation-failure-response packet の `failing_contract`、`observation_level`、
   `cause_classification`、`intent_preservation`、`evidence` を記録します。
   `intent_preservation` は same-intent repair / owner-route repair / residual
   classification / escalation route を示します。pass 目的の scope 縮小、
   link / heading oracle weakening、または validation downscope で閉じてはいけません。

## Runtime Contract Clauses

The runtime discovery adapter delegates these required operating clauses to this canonical owner.

1. Read the canonical [`md-style-check`](md-style-check.md) document.
1. Check [`coding-conventions-project.md`](../../documents/conventions/coding-conventions-project.md) and
   [`05_docs.md`](../../documents/conventions/common/05_docs.md).
1. Treat plain `md-style-check` or `$md-style-check` in a user request as an explicit skill invocation, not only a candidate signal.
1. Select this skill when a repo-changing task edits Markdown files or routes docs lint, link, heading, Mermaid, markdown math, docs-check, formatter, or `agent-canon docs` failures.
1. Use this skill with the changed document's owner. Follow [Purpose](#purpose)
   for structural-work applicability; Markdown or claim/evidence edits alone do
   not require prose-graph/structure planning or a record of unselected work.
1. For typo/link/format-only edits, do not require runtime `SKILL.md` reading
   before running the docs tool or patching. Keep owner, existing-tool route,
   and targeted-validation evidence.
1. Follow [Required Checks](#required-checks) for owner selection and command applicability. Use the project-owned route directly for project documentation; the conditional AgentCanon examples are not a second required gate.
1. Use the selected tool's help for command options and examples before reading implementation files.
1. Before formatting files with display math, normalize display math to standalone double-dollar delimiter lines with blank lines around the block. Do not nest Markdown display delimiters inside KaTeX / math fenced blocks.
1. Inline math in prose must use `$...$` (for example, `$(式)$`). Do not put math in inline code backticks, and do not use double-dollar display delimiters inside a sentence. Reserve double-dollar delimiters for display math on standalone delimiter lines.
1. Mathematical expressions must not be placed in fenced code blocks labeled `text`, `plaintext`, `txt`, `plain`, `math`, `latex`, or `tex`; these first info tokens are checked case-insensitively. Convert those to `$...$` for inline math or a standalone double-dollar block. The checker reports one finding at a declared math-like fence and payload-line findings for text-like syntax.
1. Use the selected documentation check's report for the properties it covers; open only the reported path and nearby lines when a repair needs prose context. Do not attribute untested properties to that report.
1. After a formatter or fixer runs, validate the result through the same owner's required checks. Reuse an adjacent check already run by that command rather than repeating it or adding another checker.
1. Use the owner-selected formatter/fixer when available for math or Mermaid repairs. If it escapes or duplicates display delimiters, repair the block form and recheck the changed result through that route.
1. Check heading hierarchy, command/path formatting, Mermaid fenced blocks, markdown math, and broken links together.
1. Treat broken links and heading drift as real findings.
1. Last, inspect formatter-sensitive inline math and inline code in tables. A table cell must not contain a raw `|` inside backticks or inline math; if the formatter escapes backticks or splits a cell, split the expression out of the table, replace the cell with a short name, or otherwise repair the rendered Markdown, then validate the changed result through the selected documentation route.
1. If a docs formatter/fixer/checker failure drives repair, record the
   validation-failure-response packet (`failing_contract`, `observation_level`,
   `cause_classification`, `intent_preservation`, and `evidence`). Use
   `intent_preservation` for the same-intent repair / owner-route repair /
   residual classification / escalation route. Do not close a docs-check failure by
   pass-only scope shrink, link/heading oracle weakening, or validation
   downscope.
