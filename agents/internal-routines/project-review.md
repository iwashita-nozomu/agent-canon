# project-review
<!--
@dependency-start
contract agent-runtime
responsibility Documents project-review for this repository.
upstream design ../canonical/skills.md skill canon registry
@dependency-end
-->


## Purpose

repo 全体を横断して、構成、文書、skills、ツール、静的健全性、運用 drift をまとめてレビューします。

## Use When

- repo-wide な棚卸し
- workflow、agent system、tools、docs をまたぐ全体レビュー
- 大きな整理や統合変更の完了判定
- stale 文書、重複定義、未参照資産、運用 drift の検出

## Core References

- [agents/internal-routines/comprehensive-review.md](comprehensive-review.md)
- [agents/internal-routines/project-health.md](project-health.md)
- [documents/conventions/REVIEW_PROCESS.md](../../documents/conventions/REVIEW_PROCESS.md)
- [documents/codex/AGENTS_COORDINATION.md](../../documents/codex/AGENTS_COORDINATION.md)
- [documents/conventions/coding-conventions-project.md](../../documents/conventions/coding-conventions-project.md)

## Expected Outcome

- repo 全体の `fix now`、`follow-up`、`delete-ok` が分かる
- docs、skills、workflow、tooling のどこが正本でどこが drift しているか分かる
- 局所修正で済むか、repo-wide 改造へ進むか判断できる

## Review scope

依頼された範囲で、入口と正本の関係、文書やツールの古い参照、運用上のずれを確認します。
状態の確認に必要なコマンドや個別の検証は、見つかった兆候と変更箇所から選びます。
作業ツリーの状態が論点なら Git の実状態を確認します。修正する箇所と根拠を findings に残します。

## Boundary

- 局所 diff のレビューだけなら [`change-review`](../skills/change-review.md) を使います。
- Python 差分の静的解析中心レビューなら `python-review` を使います。
- native 差分の build / header / ownership 中心レビューなら `cpp-review` を使います。
- 実験 result や report の妥当性は `critical-review` と `report-review` を使います。
