# worktree-start
<!--
@dependency-start
responsibility Documents worktree-start for this repository.
@dependency-end
-->


## Purpose

新しい worktree を切った直後、または既存 worktree を引き継いだ直後に、最初の 10 分で scope、参照、action log、carry-over 先、初期チェックを固定します。

## Use When

- new / recreated worktree の kickoff
- stale な worktree の再開前確認
- `WORKTREE_SCOPE.md` の再作成や scope refresh
- handoff 前提で worktree の入口を作り直したいとき

## Core References

- `documents/worktree-lifecycle.md`
- `documents/WORKTREE_SCOPE_TEMPLATE.md`
- `documents/BRANCH_SCOPE.md`
- `notes/guardrails/README.md`
- `notes/failures/README.md`
- `notes/worktrees/README.md`
- `notes/worktrees/WORKTREE_LOG_TEMPLATE.md`
- `notes/branches/README.md`
- `reports/agents/<run-id>/user_request_contract.md`
- `tools/setup_worktree.sh`
- `tools/worktree_start.sh`
- `tools/agent_tools/worktree_start.py`
- `tools/agent_tools/worktree_scope_lint.py`
- `tools/experiments/sync_experiment_registry_context.py`
- `tools/docs/check_worktree_scopes.sh`

## Expected Outcome

- `WORKTREE_SCOPE.md` が current state に合わせて埋まっている
- action log の path が決まり、最初の kickoff entry が残っている
- user request contract の path が決まり、action log から clause ID を辿れる
- 必要なら branch summary の path が決まり、handoff 先をそこから辿れる
- 初期状態の `git` / worktree チェック結果と次の一手が残っている
- `python3 tools/agent_tools/work_log.py ...` で継続ログを追記できる

## Mandatory Checklist

- `WORKTREE_SCOPE.md` の `Branch`、`Worktree path`、`Purpose`、`Owner or agent` が current state と一致する
- `Editable Directories`、`Runtime Output Directories`、`Read-Only Or Avoid Directories` が placeholder ではなく concrete path で埋まっている
- `Required References Before Editing` に broad directory 名ではなく concrete file や確認対象 command を書く
- `Main Carry-Over Targets` と `Working Notes During Execution` に action log path、branch summary path、主な result の置き場を書く
- `notes/worktrees/worktree_<topic>_YYYY-MM-DD.md` の path を決め、最初の kickoff entry を追記する
- `reports/agents/<run-id>/user_request_contract.md` の path を決め、最初の action がどの clause ID を処理するか固定する
- この worktree が experiment topic を持つ場合は、`experiments/registry.toml` の `active_branch` と必要なら `scope_file` / `active_worktree` を更新する
- branch が複数 session 続く、または handoff する場合は `notes/branches/<branch_topic>.md` を作るか更新する
- この branch で必要な pre-commit check を `WORKTREE_SCOPE.md` に固定する
- `git status --short --branch` を確認し、unexpected dirty state があれば action log に残す
- `git worktree list --porcelain` を確認し、duplicate / stale worktree が無いか見る
- `notes/guardrails/README.md` と `notes/failures/README.md` を読み、今の task で踏みやすい avoid pattern と既知 failure を確認する
- `python3 tools/agent_tools/worktree_scope_lint.py --current` か `bash tools/worktree_start.sh --current` で scope の placeholder や stale field を潰す
- 複数 worktree がある、または stale な再開で不安がある場合は `bash tools/docs/check_worktree_scopes.sh` を実行する
- conflict risk、scope drift、carry-over 漏れの兆候があれば、編集前に action log に残す

## Default Kickoff Sequence

1. `bash tools/worktree_start.sh <branch-name> [worktree-path]` か `python3 tools/agent_tools/worktree_start.py --current` で worktree の kickoff summary を出し、`WORKTREE_SCOPE.md` と action log の不足を洗います。
1. `documents/WORKTREE_SCOPE_TEMPLATE.md` を基に `WORKTREE_SCOPE.md` を current state へ合わせて更新し、`python3 tools/agent_tools/worktree_scope_lint.py --current` で placeholder や stale field を確認します。
1. experiment topic を持つ branch なら `experiments/registry.toml` の entry を見て、`active_branch`、必要なら `active_worktree` と `scope_file` を current state に合わせます。
1. `notes/worktrees/WORKTREE_LOG_TEMPLATE.md` を基に action log を作るか更新し、最初の kickoff entry を書きます。
1. 以後の継続ログは `python3 tools/agent_tools/work_log.py --kind <kind> --request-clause-id R1 --message "<what changed>" --next "<next>"` を既定にし、entry に `request_clause_ids=` を残します。
1. `notes/guardrails/README.md` と `notes/failures/README.md` を見て、今回の task で避けるべき既知 pattern を拾います。
1. `git status --short --branch`、`git worktree list --porcelain`、必要なら `bash tools/docs/check_worktree_scopes.sh` を実行します。
1. 次の一手と carry-over 先を action log に書いてから編集を始めます。

## Default Commands

- `bash tools/worktree_start.sh <branch-name> [worktree-path]`
- `python3 tools/agent_tools/worktree_start.py --current`
- `python3 tools/agent_tools/worktree_scope_lint.py --current`
- `python3 tools/experiments/sync_experiment_registry_context.py --topic <topic> --branch <branch>`
- `cp notes/worktrees/WORKTREE_LOG_TEMPLATE.md notes/worktrees/worktree_<topic>_YYYY-MM-DD.md`
- `python3 tools/agent_tools/work_log.py --kind edit --request-clause-id R1 --message "..." --next "..."`
- `git status --short --branch`
- `git worktree list --porcelain`
- `bash tools/docs/check_worktree_scopes.sh`

## Boundary

- cleanup readiness や delete 可否の review は `worktree-health` を使います。
- artifact の置き場は `agents/canonical/ARTIFACT_PLACEMENT.md` を正本にします。
- repo-wide な routing や CI / Docker review は `comprehensive-development` か `environment-maintenance` を使います。
- Docker / dependency / CI の変更が主題なら `environment-maintenance` を使います。
