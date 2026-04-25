# static-check
<!--
@dependency-start
@dependency-end
-->


## Purpose

実装変更の直後に、速く回せる基礎検査をまとめて扱います。

## Use When

- 型エラーの早期検出
- pytest の早期失敗確認
- Markdown とリンクの基礎確認
- Docker / 実行環境の破綻確認

## Core References

- `agents/skills/static-validation.md`
- `documents/tools/README.md`
- `tools/ci/run_all_checks.sh`
- `tools/ci/run_docs_checks.sh`
- `tools/ci/check_docker_build.sh`

## Expected Outcome

- 今回の変更に対して最低限必要な gate が実行されている
- `pass / fail / 未実行` が短く整理されている
- deeper review や追加 validation が必要か判断できる

## Check Selection

- agent runtime、skill、mirror を触ったら `make agent-checks` を先に実行します。
- code / docs 変更では、まず `make ci-quick` を基礎 gate にします。
- Markdown 中心の変更では `make docs-check` を追加します。
- Docker / runtime / dependency 変更では `make docker-build-check` を追加します。
- 失敗が出た場合は、ad hoc にコマンドを増やす前に、どの gate が不足しているかを明示します。

## Default Sequence

1. 変更対象を見て、code、docs、runtime、agent のどこを触ったかを固定します。
1. 最低限必要な gate を選び、`make agent-checks`、`make ci-quick`、`make docs-check`、`make docker-build-check` から組み合わせます。
1. 速い gate を先に実行し、失敗したらその時点で原因を切り分けます。
1. 追加の深い検証が必要なら `static-validation` へ進みます。
1. closeout では、通ったもの、失敗したもの、まだ回していないものを分けて残します。

## Default Commands

- `make agent-checks`
- `make ci-quick`
- `make docs-check`
- `make docker-build-check`

## Boundary

- この repo では `static-validation` が基礎 gate の正本です。
- 深い diff review は `change-review` または `code-review` を使います。
