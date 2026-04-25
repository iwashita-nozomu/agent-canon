# Worktree Notes
<!--
@dependency-start
@dependency-end
-->


このディレクトリには、active な worktree の kickoff から closeout までを追う action log と carry-over note を置きます。
研究・実験改造の全体手順は [agents/workflows/research-workflow.md](../../agents/workflows/research-workflow.md) を参照してください。

## Purpose

- worktree を切った直後の kickoff 状態を `main` 側から辿れるようにする
- 削除前の worktree にしか残っていない知見を `main` 側へ退避する
- 一時的な branch や tuning worktree の判断を、後で参照できる形にする
- worktree 自体は消しても、判断の履歴は失わないようにする

## Action Log

- このディレクトリの note は、carry-over 用 summary であると同時に worktree の action log の正本です。
- scope 更新、編集開始、テスト実行、実験開始 / 停止、最終判断は append-only で追記します。
- 1 行でよいので、何をしたか、何を見たか、次に何をするかが追える形にします。
- worktree 内で先に書く場合も、最終配置と同じ相対パスに置きます。
- 追記は `python3 tools/agent_tools/work_log.py --kind <kind> --message "<what changed>" --next "<next>"` を既定にします。`WORKTREE_SCOPE.md` に contract path が入っていれば、同じ command で run bundle `work_log.md` も更新されます。
- work block を始めたら kickoff / resume、終えたら test / review / closeout を最低 1 行ずつ残します。

## Kickoff Minimum

worktree を作った直後は、最低限次を残します。

- branch 名、worktree path、purpose
- `WORKTREE_SCOPE.md` の所在と main carry-over target
- `notes/guardrails/README.md` と `notes/failures/README.md` を見たか、その中で今回 relevant な項目
- `git status --short --branch` と `git worktree list --porcelain` の確認結果
- 今から最初にやる 1 手

## Template

- kickoff と継続記録には [WORKTREE_LOG_TEMPLATE.md](/mnt/l/workspace/project_template/notes/worktrees/WORKTREE_LOG_TEMPLATE.md) を使います。
- closeout で再利用知識へ昇格させるときは `documents/notes-lifecycle.md` を見ます。

## What To Extract

最低限、次を整理してから worktree を消します。

- branch 名
- worktree の用途
- 関連する result や log の所在
- 主要な観測
- 次に残すべき `Idea:` / `Interpretation:` / `Consideration:`
- その worktree を一度しか開かなくても状況が分かる quick reference

## Naming

- ファイル名は `worktree_<topic>_YYYY-MM-DD.md` のように、対象が分かる形にします。
- unrelated な worktree を 1 つの file に混ぜません。
- タイトルは日付ではなく topic を主にします。

## Recommended Sections

- `Summary:`
- `Action Log:`
- `Question / Formulation:`
- `Observations:`
- `Carry-Over Targets:`
- `Branch Reflection:`
- `Idea:` / `Interpretation:` / `Consideration:`
