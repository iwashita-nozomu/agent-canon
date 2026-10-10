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

Issue に紐づく repository task では、対象 Issue と最新 comment から要求や
途中状態を復元し、その後に current source で確認します。Issue の記述は
要求の証拠ですが、現在の code state を置き換えません。Issue が task と
結び付かない場合、Issue を開始条件として捏造しません。

- user が Issue 番号または URL を示した場合は、その Issue を最初に開きます。
- Issue 番号が明示されていなくても、task id、PR、branch、commit、既知の owner/path から対応 Issue が一意に辿れる場合は、その Issue と最新 comment を最初に読みます。
- Issue から linked PR、branch、topic clone/worktree、draft、progress comment、handoff、validation evidence を辿り、同じ task の途中作業を復元します。
- Issue に途中状態が記録されている場合は、main だけを見て未着手と判断せず、その continuation surface を確認します。
- Issue が存在しない task では、Issue を捏造して開始条件にしません。新規 Issue 作成が request または backlog workflow の責務なら、その owner route に従います。

## In-Progress Work First

新しい branch、topic checkout、PR、または writer handoff を作る判断が
必要なときは、同じ task に結び付く既存作業を先に探します。Issue/task ID、
owner/path、既知の branch を手掛かりに、関連する PR、branch、topic checkout、
draft、handoff、validation evidence を bounded に確認します。要求、owner、
責務、branch identity、validation route が互換なら既存作業から続けます。
再利用できない場合は、stale、conflicting、scope-incompatible、または owner
evidence 不一致のうち該当する理由を記録します。無関係な branch や artifact
を全走査せず、main に未反映という理由だけで未着手と判断しません。

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

Choose the next source from the unresolved question. Start at the active root
[AGENTS.md](../../AGENTS.md) and the selected Skill to find the owner. If the
repository or affected area is unfamiliar, use the relevant overview—such as
`README.md`, `QUICK_START.md`, [documents/README.md](../../documents/README.md),
[agents/workflows/README.md](../workflows/README.md), `docker/README.md`,
[agents/README.md](../README.md), [tools/README.md](../../tools/README.md), or
`scripts/README.md`—that helps explain the path in scope. Codex task routing uses
[CODEX_WORKFLOW.md](../canonical/CODEX_WORKFLOW.md). These are orientation
sources, not a list to read end to end for every task. For an Issue-backed task,
use the Issue and compatible continuation evidence before deciding whether to
create new work; then verify current code and owner constraints.

## Outputs

- Issue-backed task なら Issue の current requirement / progress state の短い readback
- resume する既存 work の PR / branch / topic clone / worktree、または compatible な途中作業が無いという短い readback
- repo shape の短い要約
- 触るべきディレクトリ
- 追加で読むべき正本
- selected Skill / operational owner と、次の判断に使った source evidence
- 未完了で handoff / stop する場合は Issue progress comment の URL または comment identity
