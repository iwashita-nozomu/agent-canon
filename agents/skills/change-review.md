# change-review
<!--
@dependency-start
upstream design ../canonical/skills.md skill canon registry
@dependency-end
-->


## Purpose

diff を findings-first で読み、回帰、欠落テスト、古い文書を洗います。

## Use When

- code review
- doc review
- AI-generated diff review

## Core Reference

- `documents/REVIEW_PROCESS.md`

## Expected Outcome

- findings が summary より先に並んでいる
- `fix now` と `follow-up` が分かれている
- review で見ていない範囲や validation gap が残っている

## Mandatory Checklist

- 実際の diff を先に読んでいる
- change set の意図と影響範囲を把握している
- `bash tools/agent_tools/run_repo_dependency_review.sh` を全 repo に対して実行し、`--changed` だけで済ませていない
- 回帰、欠落テスト、stale documentation を優先して見ている
- 必要な validation が走っているか、未実行なら明記している
- `no findings` の場合でも residual risk を残している

## Default Sequence

1. `git diff --stat` と `git diff --name-only` で変更面を固定します。
1. 破壊的変更、削除、rename、config 変更を先に見ます。
1. docs と tests が実装に追随しているか確認します。
1. `bash tools/agent_tools/run_repo_dependency_review.sh` を実行し、全 repo の dependency manifest coverage / format / graph を確認します。
1. findings を priority 順に並べ、evidence を付けます。
1. summary は findings の後に短く付けます。

## Findings Buckets

- `fix now`
- `follow-up`
- `delete-ok`

## Boundary

- Python 差分で型と test を強く見る場合は `python-review` を追加します。
- C / C++ 差分で build、header、ownership を強く見る場合は `cpp-review` を追加します。
