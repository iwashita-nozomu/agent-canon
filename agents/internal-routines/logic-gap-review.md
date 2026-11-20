# logic-gap-review
<!--
@dependency-start
contract agent-runtime
responsibility Documents logic-gap-review for this repository.
upstream design ../canonical/skills.md skill canon registry
upstream design ../skills/prose-reasoning-graph.md prose graph logic diagnostic overlay
@dependency-end
-->


## Purpose

学術文章の主張が、citation、data、derivation、前 paragraph の結論から本当に繋がっているかをレビューします。

## Use When

- 論文、thesis chapter、method note の claim review
- result から interpretation への飛躍が疑われる
- paragraph ごとの inference が暗黙になりやすい

## Core References

- [agents/skills/academic-writing.md](../skills/academic-writing.md)
- [agents/internal-routines/critical-review.md](critical-review.md)
- [documents/conventions/REVIEW_PROCESS.md](../../documents/conventions/REVIEW_PROCESS.md)

## Review criteria

主張を定義、仮定、引用、観測、導出に照らし、結論までの推論が成立するか確かめます。
根拠の及ぶ範囲、暗黙の仮定、反証や別の解釈が結論を変える場合は、該当する主張を示します。
prose graph の診断は、実際の本文と照合して判断します。

## Boundary

- 記号や略語の定義順は `notation-definition-review` を使います。
- reader path や section order は `document_flow_reviewer` を使います。
