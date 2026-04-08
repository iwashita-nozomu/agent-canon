# notation-definition-review

## Purpose

記号、略語、technical term、仮定、unit、index の definition-before-use と一貫性をレビューします。

## Use When

- 数式や記号が多い文書
- 略語や専門用語の密度が高い文書
- appendix、method note、theory note、supplementary material

## Core References

- `documents/academic-writing-workflow.md`
- `documents/long-form-writing-workflow.md`
- `documents/REVIEW_PROCESS.md`

## Mandatory Checklist

- 新しい quantity、symbol、abbreviation を導入時に定義している
- 同じ concept に複数の語や複数の記号を当てていない
- 似た記号、添字、集合、index の区別が明示されている
- unit、domain、shape、type が reader に追える
- assumption や convention が後出しになっていない
- 用語の意味が section を跨いでぶれていない

## Default Sequence

1. symbol、abbreviation、technical term を拾います。
1. 初出箇所と definition を照合します。
1. overloaded notation、late definition、ambiguous reference を findings 化します。
1. unit、domain、index、assumption の不足を findings 化します。
1. author が慣れているから分かるだけの notation を通しません。

## Boundary

- 推論の飛躍は `logic-gap-review` を使います。
- 文書全体の reader path は `document_flow_reviewer` を使います。
