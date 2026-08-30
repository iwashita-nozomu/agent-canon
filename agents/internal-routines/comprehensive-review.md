# comprehensive-review
<!--
@dependency-start
contract agent-runtime
responsibility Documents comprehensive-review for this repository.
upstream design ../canonical/skills.md skill canon registry
@dependency-end
-->


## Purpose

repo 全体を横断して、文書、skill、ツール、統合設定の破綻をまとめて検査します。

## Use When

- 文書体系の棚卸し
- skill 間の重複や未整合の確認
- 自動化や integration point の確認
- repo-wide な整理や workflow 改造の完了判定

## Core References

- `documents/runtime/runtime-profiles-and-check-matrix.md`
- `agents/internal-routines/project-review.md`

## Expected Outcome

- repo-wide な static health と workflow health を一括で見られる
- どの validator が通り、どこが壊れているかをまとめて把握できる
- 個別修正へ戻るか、repo-wide cleanup を続けるか判断できる

## Selection

`project-review` が inventory と責務範囲を確認し、repo-wide な調査が必要な
場合だけこの route を選びます。選択した profile の validator を実行し、
その失敗を個別に再現できる形で記録します。この文書は独自の checklist や
command set を所有せず、profile 外の validator を追加しません。

## Boundary

- 局所 diff のレビューだけなら `code-review` を使います。
- repo-wide review の最上位入口としては `project-review` を使います。
- 研究系の独立視点 review は `research-perspective-review` を使います。
- profile activation と check の対応は `documents/runtime/runtime-profiles-and-check-matrix.md` が所有します。
