# repo-onboarding
<!--
@dependency-start
contract skill
responsibility Documents repo-onboarding for this repository.
upstream design ../canonical/skills.md skill canon registry
@dependency-end
-->


## Purpose

unfamiliar repo やサブディレクトリに入ったとき、最短で安全に入口、コマンド、正本を把握します。

## Use When

- repo の全体像がまだ曖昧
- どの文書を読むべきか迷う
- task 前に前提確認が必要

## In-Progress Work First

新規調査、branch、topic clone、worktree、PR、または writer handoff を作る前に、同じ task の途中作業を優先して探します。

- issue / task id、対象 owner/path、既知の branch 名を seed にして、open PR、既存 branch、issue-linked topic clone/worktree、draft、進捗 comment、handoff / validation evidence を確認します。
- user request、owner、replaceable responsibility、branch identity、validation route が互換な途中作業があれば、新規 workstream を作らずその作業を resume します。既存 PR がある場合はその head を continuation owner として扱います。
- 途中作業の探索は task に結び付く bounded lookup を優先し、無関係な branch / PR / artifact の全走査を開始条件にしません。
- 既存 work が stale、conflicting、scope-incompatible、または owner evidence 不一致で再利用できない場合だけ新規 workstream を作り、再利用しなかった理由を短く残します。
- 「main に未反映だから未着手」と推定しません。main の current state と途中作業の両方を確認してから implementation scope を決めます。

## Read Order

1. task に対応する途中作業の有無と、その current head / state
1. `README.md`
1. `QUICK_START.md`
1. `documents/README.md`
1. `agents/workflows/README.md`
1. `docker/README.md`
1. `agents/README.md`
1. Codex なら `agents/canonical/CODEX_WORKFLOW.md`
1. `tools/README.md`
1. `scripts/README.md`

## Outputs

- resume する既存 work の PR / branch / topic clone / worktree、または compatible な途中作業が無いという短い readback
- repo shape の短い要約
- 触るべきディレクトリ
- 追加で読むべき正本
