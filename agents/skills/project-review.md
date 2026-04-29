# project-review
<!--
@dependency-start
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

- `agents/skills/comprehensive-review.md`
- `agents/skills/project-health.md`
- `documents/REVIEW_PROCESS.md`
- `documents/AGENTS_COORDINATION.md`
- `documents/coding-conventions-project.md`

## Expected Outcome

- repo 全体の `fix now`、`follow-up`、`delete-ok` が分かる
- docs、skills、workflow、tooling のどこが正本でどこが drift しているか分かる
- 局所修正で済むか、repo-wide 改造へ進むか判断できる

## Mandatory Phases

1. `Inventory`
   - 主要ディレクトリ、入口文書、skills、workflow family、automation 入口を洗います。
1. `Static Health`
   - `make agent-checks`、`make ci-quick`、必要なら `bash tools/run_comprehensive_review.sh` を見ます。
1. `Workflow Health`
   - `AGENTS.md`、`agents/`、`documents/` の導線が一致しているかを見ます。
1. `Tooling Health`
   - Docker、CI、dependency、補助 script の stale 化を見ます。
1. `Worktree Health`
   - worktree、branch、carry-over、cleanup 忘れを確認します。
1. `Follow-Up Decision`
   - findings を即修正、後続、削除候補に分けます。

## Default Sequence

1. review の対象範囲を固定し、repo-wide で見るべき面を列挙します。
1. まず inventory を取り、どの文書と script が current entrypoint かを確認します。
1. static health を通して、破綻があるなら先に stop-the-line issue として扱います。
1. workflow health と tooling health を cross-check し、正本の重複や stale route を見つけます。
1. worktree / branch / note の残骸や carry-over 漏れを確認します。
1. findings を分類し、必要なら `comprehensive-review`、`environment-maintenance`、`docs-consistency-review` へ分岐します。

## Default Commands

- `make agent-checks`
- `make ci-quick`
- `bash tools/run_comprehensive_review.sh`
- `git worktree list --porcelain`
- `rg -n \"<pattern>\" agents documents README.md QUICK_START.md AGENTS.md`

## Boundary

- 局所 diff のレビューだけなら `code-review` を使います。
- Python 差分の静的解析中心レビューなら `python-review` を使います。
- native 差分の build / header / ownership 中心レビューなら `cpp-review` を使います。
- 実験 result や report の妥当性は `critical-review` と `report-review` を使います。
