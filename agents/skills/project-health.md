# project-health
<!--
@dependency-start
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

- `documents/tools/README.md`
- `documents/REVIEW_PROCESS.md`
- `tools/run_comprehensive_review.sh`
- `tools/docker_dependency_validator.sh`

## Expected Outcome

- CI / docs / agent runtime / environment のどこに drift があるか分かる
- routine maintenance で今すぐ直すものと監視継続でよいものが分かる
- repo-wide な review を開くべきか、局所修正で済むか判断できる

## Monitoring Areas

- agent runtime と skill mirror の同期
- `make ci-quick` で見る基礎品質
- Docker / dependency / runtime の drift
- docs、workflow、tool 導線の stale 化
- 長く残っている worktree、branch、未整理 note

## Default Sequence

1. 直近の変更有無に関わらず、まず `make agent-checks` と `make ci-quick` で基礎状態を見ます。
1. 環境 drift を疑う場合は `bash tools/docker_dependency_validator.sh` を追加します。
1. repo-wide な兆候がある場合は `bash tools/run_comprehensive_review.sh` へ進みます。
1. findings を `fix now`、`follow-up`、`watch` に分けます。
1. ルール変更が必要なら `documents/` または `agents/` の正本更新へつなぎます。

## Default Commands

- `make agent-checks`
- `make ci-quick`
- `bash tools/docker_dependency_validator.sh`
- `bash tools/run_comprehensive_review.sh`

## Boundary

- 変更差分のレビューは `code-review` を使います。
- repo-wide review の最上位入口としては `project-review` を使います。
