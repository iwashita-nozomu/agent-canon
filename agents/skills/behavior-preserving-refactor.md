# behavior-preserving-refactor

## Purpose

大きめの refactor を、feature 追加ではなく挙動保存つきの再編として扱います。

## Use When

- file 分割、rename、module 境界整理
- 依存方向の整理
- implementation の差し替えを伴う構造再編
- branch 側で file 構成変更を含む整理

## Core References

- `agents/TASK_WORKFLOWS.md`
- `documents/implementation-waterfall-workflow.md`
- `documents/REVIEW_PROCESS.md`
- `documents/main-integration-workflow.md`

## Required Contract

1. refactor pass では `Behavior Contract:` を先に固定します。
1. `Allowed Structural Delta:` と `Forbidden Semantic Delta:` を分けて書きます。
1. 新機能追加は同じ pass に混ぜません。必要なら先に分離します。
1. delete、rename、move、module split は `Files To Remove Or Move:` として先に列挙します。
1. old path と new path の対応を `Path Mapping:` として残します。
1. implementation 前に `test_designer` で regression case と nasty case を固定します。
1. 既存 test が薄い場合は baseline capture を追加してから rework します。
1. closeout 前に `python3 scripts/ci/check_merge_structure.py ...` の要否を確認します。

## Review Emphasis

- `design_reviewer`
  - semantic delta が混入していないか
- `document_flow_reviewer`
  - path mapping と migration 説明が上から読んで追えるか
- `project_reviewer`
  - cross-module drift、stale path、残骸がないか
- language reviewer
  - Python なら `python-review`
  - C / C++ なら `cpp-review`
