# comprehensive-review
<!--
@dependency-start
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

- `tools/run_comprehensive_review.sh`
- `documents/tools/README.md`
- `agents/skills/project-review.md`

## Expected Outcome

- repo-wide な static health と workflow health を一括で見られる
- どの validator が通り、どこが壊れているかをまとめて把握できる
- 個別修正へ戻るか、repo-wide cleanup を続けるか判断できる

## Mandatory Checklist

- review 対象が docs、skills、tools、integration points をまたいでいる
- `tools/run_comprehensive_review.sh` の結果を確認している
- fail した validator を個別に再現できる状態で残している
- findings を repo-wide issue と局所 issue に分けている

## Default Sequence

1. `project-review` で inventory を取り、comprehensive に見る必要があるかを判断します。
1. `bash tools/run_comprehensive_review.sh` を実行します。
1. 失敗した validator の log を見て、repo-wide issue と局所 issue を切り分けます。
1. 必要に応じて `make agent-checks`、`make docs-check`、`make ci-quick` へ掘り下げます。
1. closeout では、通った validator、失敗した validator、未確認領域を残します。

## Default Commands

- `bash tools/run_comprehensive_review.sh`
- `bash tools/run_comprehensive_review.sh --parallel`
- `bash tools/run_comprehensive_review.sh --report`

## Boundary

- 局所 diff のレビューだけなら `code-review` を使います。
- repo-wide review の最上位入口としては `project-review` を使います。
- 研究系の独立視点 review は `research-perspective-review` を使います。
