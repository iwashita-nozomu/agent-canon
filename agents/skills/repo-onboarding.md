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

## Issue First

Issue に紐づく repository task では、実装、main 読み、PR/branch 探索より先に対象 Issue 本文と最新 comment を読みます。Issue は要求、既知の途中状態、過去の判断、branch/PR handoff を復元する最初の task-state source です。code の現状はその後に current main / branch で検証し、Issue の古い記述を code より優先しません。

- user が Issue 番号または URL を示した場合は、その Issue を最初に開きます。
- Issue 番号が明示されていなくても、task id、PR、branch、commit、既知の owner/path から対応 Issue が一意に辿れる場合は、その Issue と最新 comment を最初に読みます。
- Issue から linked PR、branch、topic clone/worktree、draft、progress comment、handoff、validation evidence を辿り、同じ task の途中作業を復元します。
- Issue に途中状態が記録されている場合は、main だけを見て未着手と判断せず、その continuation surface を確認します。
- Issue が存在しない task では、Issue を捏造して開始条件にしません。新規 Issue 作成が request または backlog workflow の責務なら、その owner route に従います。

## In-Progress Work First

新規調査、branch、topic clone、worktree、PR、または writer handoff を作る前に、同じ task の途中作業を優先して探します。

- Issue / task id、対象 owner/path、既知の branch 名を seed にして、open PR、既存 branch、issue-linked topic clone/worktree、draft、進捗 comment、handoff / validation evidence を確認します。
- user request、owner、replaceable responsibility、branch identity、validation route が互換な途中作業があれば、新規 workstream を作らずその作業を resume します。既存 PR がある場合はその head を continuation owner として扱います。
- 途中作業の探索は task に結び付く bounded lookup を優先し、無関係な branch / PR / artifact の全走査を開始条件にしません。
- 既存 work が stale、conflicting、scope-incompatible、または owner evidence 不一致で再利用できない場合だけ新規 workstream を作り、再利用しなかった理由を短く残します。
- 「main に未反映だから未着手」と推定しません。Issue、main、途中作業を照合して implementation scope を決めます。

## Issue Progress Writeback

Issue-backed task は、作業が未完了の状態で handoff、停止、別 task への移動、または user turn の終了に入る前に、対象 Issue へ current state を comment します。chat や PR body だけに途中状態を残しません。

進捗 comment は短く、次の continuation に必要な事実だけを持ちます。

- current branch / PR / head commit
- 完了した責務または検証
- 未完了の責務
- blocker がある場合は blocker と、その原因が branch defect か外部要因か
- 次に実行する具体的な action

同じ状態を繰り返し comment しません。branch、PR、validation、blocker、remaining work のいずれかが実質的に変わったときに更新します。Issue が完了して close できる場合は途中状態 comment の代わりに最終 evidence と close reason を残します。

## Read Order

1. task に対応する Issue 本文と最新 comment
1. Issue から辿れる途中作業の current head / state
1. current main と途中作業との差分
1. active root `AGENTS.md` の Reader Map row
1. selected canonical Skill の operational section と、同 section が必要時に委譲する owner
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

- Issue-backed task なら Issue の current requirement / progress state の短い readback
- resume する既存 work の PR / branch / topic clone / worktree、または compatible な途中作業が無いという短い readback
- repo shape の短い要約
- 触るべきディレクトリ
- 追加で読むべき正本
- `agent-orchestration.md#Owner-First-Read-Trace` の operational-owner readback。未解決なら
  implementation path を列挙せず `implementation_read=locked` とする
- 未完了で handoff / stop する場合は Issue progress comment の URL または comment identity
