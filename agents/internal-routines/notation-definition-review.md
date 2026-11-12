# notation-definition-review
<!--
@dependency-start
contract agent-runtime
responsibility Documents notation-definition-review for this repository.
upstream design ../canonical/skills.md skill canon registry
@dependency-end
-->


## Purpose

記号、略語、専門用語、仮定、単位、添字を使う前に意味が説明され、本文で一貫しているかを確認します。

## Use When

- 数式や記号が多い文書
- 略語や専門用語の密度が高い文書
- 一般の説明・進捗・完了報告で、用語の意味や表記が読み取りにくい場合
- appendix、method note、theory note、supplementary material

## Core References

- [agents/skills/academic-writing.md](../skills/academic-writing.md)
- [agents/skills/long-form-writing.md](../skills/long-form-writing.md)
- [documents/conventions/REVIEW_PROCESS.md](../../documents/conventions/REVIEW_PROCESS.md)
- [用語と翻訳の判断](verification-result-structuring.md#terms-and-translation)

## 確認事項

- 読者に必要な新しい量、記号、略語、専門用語を初出で説明している
- 同じ概念に複数の語や複数の記号を当てていない
- 似た記号、添字、集合の区別が明示されている
- 単位、対象の範囲、データの形や型を読者が追える
- 仮定や表記の約束が後出しになっていない
- 用語の意味がセクションを跨いでぶれていない
- 慣用的な専門用語と原典の名称を保ち、不自然な訳語や新しい意味を作っていない

## Default Sequence

1. 読者が理解する必要のある記号、略語、専門用語を拾います。
1. 初出の説明を、原典や実装での定義と照合します。不要な内部用語は具体的な操作や対象で説明します。
1. 同じ記号の意味の衝突、説明の後出し、曖昧な参照、不自然な訳語を指摘します。
1. 単位、対象の範囲、添字、仮定の説明が足りない箇所を指摘します。
1. 読者が本文と参照先から意味を理解できるかを確認します。

## Boundary

- 推論の飛躍は `logic-gap-review` を使います。
- 文書全体の reader path は `document_flow_reviewer` を使います。
