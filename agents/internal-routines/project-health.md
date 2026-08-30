# project-health
<!--
@dependency-start
contract agent-runtime
responsibility Documents project-health for this repository.
upstream design ../canonical/skills.md skill canon registry
@dependency-end
-->


## Purpose

日次・週次・継続運用での健康状態を監視し、automation の壊れ方を早めに見つけます。

## Use When

- project health の監視
- CI / CD 健全性確認
- routine maintenance の起点作り
- 運用上の drift 検出

## Core References

- `documents/runtime/runtime-profiles-and-check-matrix.md`
- `documents/conventions/REVIEW_PROCESS.md`
- `agents/internal-routines/project-review.md`

## Expected Outcome

- CI / docs / agent runtime / environment のどこに drift があるか分かる
- routine maintenance で今すぐ直すものと監視継続でよいものが分かる
- repo-wide な review を開くべきか、局所修正で済むか判断できる

## Monitoring Areas

- agent runtime と skill mirror の同期
- 基礎品質の drift（profile は runtime matrix で選択）
- Docker / dependency / runtime の drift
- docs、workflow、tool 導線の stale 化
- 長く残っている worktree、branch、未整理 note

## Selection

変更や観測した drift の責務を `documents/runtime/runtime-profiles-and-check-matrix.md`
で分類し、該当 profile の route だけを選びます。直近の変更がないという
理由で基礎 command を一律に実行しません。repo-wide な兆候がある場合だけ
`project-review` に調査を委譲し、findings を `fix now`、`follow-up`、`watch`
に整理します。

## Boundary

- 変更差分のレビューは `code-review` を使います。
- repo-wide review の最上位入口としては `project-review` を使います。
- profile の activation と check の対応は runtime profile/check matrix が所有します。
