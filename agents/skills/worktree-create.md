# Worktree Create

## Purpose

新しい worktree を切り、`WORKTREE_SCOPE.md` を「placeholder なしで次の作業へ渡せる品質」まで引き上げます。

## Use This For

- new / recreated worktree を切るとき
- missing / stale `WORKTREE_SCOPE.md` を作り直すとき
- branch / worktree の create と scope drafting を 1 つの手順で閉じたいとき
- `WORKTREE_SCOPE.md` の quality が低く、placeholder を残したまま kickoff しがちなとき

## Must Read Before Using

- `documents/worktree-lifecycle.md`
- `documents/WORKTREE_SCOPE_TEMPLATE.md`
- `notes/guardrails/README.md`
- `notes/guardrails/engineering_avoidances.md`
- `notes/failures/README.md`
- `notes/failures/setup_worktree_detached_head_2026-04-06.md`

## Inputs

- branch 名
- custom path を使う場合の worktree path
- target module / runtime
- 目的と非ゴールの draft
- 初期の editable directories、runtime output directories、carry-over target

## Outputs

- create または reuse 済みの worktree
- branch / path / action log / branch summary が concrete に入った `WORKTREE_SCOPE.md`
- `WORKTREE_SCOPE.md` quality findings
- quality findings を潰したあとの kickoff 入口

## Quick Path

1. `bash scripts/worktree_start.sh <branch-name> [worktree-path]` を実行する
1. 生成された `WORKTREE_SCOPE.md` の `Purpose`、`Editable Directories`、`Runtime Output Directories`、`Required References Before Editing`、`Required Checks Before Commit` を concrete に埋める
1. current worktree の quality 確認には `python3 scripts/agent_tools/worktree_scope_lint.py --workspace-root <worktree-path>`、live worktree 全体の棚卸しには `bash scripts/tools/check_worktree_scopes.sh` を実行する
1. placeholder と missing reference が消えるまで `WORKTREE_SCOPE.md` を直す
1. scope 契約の鋭さまで見るなら `workscope-review` を通す
1. quality error が消えたら `worktree-start` へ handoff する

## Mandatory Checklist

- `WORKTREE_SCOPE.md` の `Purpose` に target module / runtime、主目的、非ゴールが入っている
- `Editable Directories` と `Read-Only Or Avoid Directories` が concrete path で埋まっている
- `Required References Before Editing` に core reference だけでなく topic-specific file が入っている
- `Working Notes During Execution` の action log path と branch summary path が concrete である
- `Required Checks Before Commit` に実際に叩く command が入っている
- `TODO`、`<topic>`、`documents/...`、`pytest ...` などの placeholder が残っていない
- current worktree の lint error が消えている

## Default Commands

- `bash scripts/worktree_start.sh <branch-name> [worktree-path]`
- `python3 scripts/agent_tools/worktree_scope_lint.py --workspace-root <worktree-path>`
- `bash scripts/tools/check_worktree_scopes.sh`

## Boundary

- 既存 worktree の resume や handoff は `agents/skills/worktree-start.md` を使います。
- scope 契約の independent review は `agents/skills/workscope-review.md` を使います。
- current worktree の drift や cleanup readiness は `agents/skills/worktree-health.md` を使います。
- docs / workflow の repo-wide review は `agents/skills/project-review.md` を使います。

## Implementation Surface

- `scripts/worktree_start.sh`
- `scripts/setup_worktree.sh`
- `scripts/agent_tools/worktree_start.py`
- `scripts/agent_tools/worktree_scope_lint.py`
- `scripts/tools/check_worktree_scopes.sh`
