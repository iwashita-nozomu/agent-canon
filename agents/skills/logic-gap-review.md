# logic-gap-review
<!--
@dependency-start
upstream design ../canonical/skills.md skill canon registry
@dependency-end
-->


## Purpose

学術文章の主張が、citation、data、derivation、前 paragraph の結論から本当に繋がっているかをレビューします。

## Use When

- 論文、thesis chapter、method note の claim review
- result から interpretation への飛躍が疑われる
- paragraph ごとの inference が暗黙になりやすい

## Core References

- `agents/workflows/academic-writing-workflow.md`
- `agents/skills/critical-review.md`
- `documents/REVIEW_PROCESS.md`

## Mandatory Checklist

- 各 main claim に support が追跡できる
- result と interpretation が混ざっていない
- 段落間の依存関係が reader に追える
- 暗黙の仮定、前提、boundary condition が露出している
- 文献 citation が claim の重さに見合っている
- limitation や alternative explanation を隠していない

## Default Sequence

1. central contribution と subclaim を列挙します。
1. 各 subclaim がどの evidence に依存するかを追います。
1. unsupported leap、hidden assumption、premature conclusion を findings 化します。
1. result / interpretation / speculation / future work の混線を findings 化します。
1. logic の修正を wording の修正より先に要求します。

## Boundary

- 記号や略語の定義順は `notation-definition-review` を使います。
- reader path や section order は `document_flow_reviewer` を使います。
