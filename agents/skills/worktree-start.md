# worktree-start
<!--
@dependency-start
contract skill
responsibility Documents worktree-start for this repository.
upstream design ../canonical/skills.md skill canon registry
downstream design ../../.agents/skills/worktree-start/SKILL.md runtime skill shim
@dependency-end
-->


## Reader Map

- Purpose: documents the legacy-only route for inspecting or retiring stale
  `WORKTREE_SCOPE.md` and action-log cleanup evidence.
- Use When: existing legacy worktree cleanup artifacts must be reviewed or
  closed, not when starting new work.
- Section path: Purpose, Use When, and Core References set scope; Expected
  Outcome, Mandatory Checklist, Default Kickoff Sequence, and Default Commands
  contain operational rules; Boundary states the hard limit.
- Boundary: do not use this skill to create, recreate, resume, or move work
  into a git worktree.

## Purpose

既存の stale worktree、古い `WORKTREE_SCOPE.md`、または過去の action log を current checkout へ持ち帰る前に、scope drift と cleanup 判断を固定します。新しい `git worktree` は作成・使用しません。

## Use When

- stale な worktree の棚卸し
- 古い `WORKTREE_SCOPE.md` の再開禁止確認
- `WORKTREE_SCOPE.md` が stale evidence かどうかの診断
- handoff 前提で legacy action log の carry-over 先を決めたいとき

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
- `tools/setup_worktree.sh` (legacy reference only; do not use for new tasks)
- `tools/worktree_start.sh` (legacy cleanup diagnostic only)
- `tools/agent_tools/worktree_start.py` (legacy cleanup diagnostic only)
- `tools/agent_tools/worktree_scope_lint.py`
- `tools/experiments/sync_experiment_registry_context.py`
- `tools/docs/check_worktree_scopes.sh`

## Expected Outcome

- stale `WORKTREE_SCOPE.md` が current checkout の scope authority ではないことを確認している
- legacy action log の carry-over 要否と持ち帰り先が決まっている
- user request contract の path が必要なら current checkout の run-local `work_log.md` から辿れる
- 必要なら branch summary の path が決まり、handoff 先をそこから辿れる
- 初期状態の `git` / worktree 棚卸し結果と cleanup の次の一手が残っている
- `python3 tools/agent_tools/work_log.py ...` で current checkout の継続ログを追記できる

## Mandatory Checklist

- `WORKTREE_SCOPE.md` の `Branch`、`Worktree path`、`Purpose`、`Owner or agent` が current state と一致しない場合は、作業 authority として使わない判断が残っている
- `Editable Directories`、`Runtime Output Directories`、`Read-Only Or Avoid Directories` は legacy evidence として読み、current checkout の write scope は handoff packet で固定する
- `Required References Before Editing` に broad directory 名ではなく concrete file や確認対象 command を書く
- `Main Carry-Over Targets` と `Working Notes During Execution` に legacy action log path、branch summary path、主な result の置き場を書く
- `notes/worktrees/worktree_<topic>_YYYY-MM-DD.md` は legacy evidence として扱い、current checkout の run-local `work_log.md` に carry-over 判断を追記する
- `reports/agents/<run-id>/user_request_contract.md` の path を決め、最初の cleanup action がどの clause ID を処理するか固定する
- 古い worktree が experiment topic を持つ場合は、`experiments/registry.toml` の stale `active_worktree` / `scope_file` を cleanup 対象にする
- branch が複数 session 続いた場合や handoff する場合は `notes/branches/<branch_topic>.md` を summary evidence として作るか更新する
- この branch で必要な pre-commit check は current checkout の run-local handoff packet に固定する
- `git status --short --branch` を確認し、unexpected dirty state があれば action log に残す
- `git worktree list --porcelain` を確認し、duplicate / stale worktree が無いか見る
- `notes/guardrails/README.md` と `notes/failures/README.md` を読み、今の task で踏みやすい avoid pattern と既知 failure を確認する
- `python3 tools/agent_tools/worktree_scope_lint.py --current` で scope の placeholder や stale field を診断する。`bash tools/worktree_start.sh --current` は cleanup diagnostic 以外では使わない
- 複数 worktree がある、または stale な再開で不安がある場合は `bash tools/docs/check_worktree_scopes.sh` を実行する
- conflict risk、scope drift、carry-over 漏れの兆候があれば、編集前に action log に残す

## Default Kickoff Sequence

1. `python3 tools/agent_tools/worktree_scope_lint.py --current` で legacy `WORKTREE_SCOPE.md` と action log の不足を診断します。新しい `git worktree` は作成しません。
1. `documents/WORKTREE_SCOPE_TEMPLATE.md` は legacy scope の照合用としてだけ読み、current checkout の作業 scope は run-local handoff packet と `work_log.md` で管理します。
1. experiment topic を持つ branch なら `experiments/registry.toml` の entry を見て、stale `active_worktree` と `scope_file` を cleanup 対象として記録します。
1. `notes/worktrees/WORKTREE_LOG_TEMPLATE.md` 由来の action log は legacy evidence として読み、current checkout の run-local `work_log.md` に carry-over 判断を書きます。
1. 以後の継続ログは `python3 tools/agent_tools/work_log.py --kind <kind> --request-clause-id R1 --message "<what changed>" --next "<next>"` を既定にし、entry に `request_clause_ids=` を残します。
1. `notes/guardrails/README.md` と `notes/failures/README.md` を見て、今回の task で避けるべき既知 pattern を拾います。
1. `git status --short --branch`、`git worktree list --porcelain`、必要なら `bash tools/docs/check_worktree_scopes.sh` を実行します。
1. 次の一手と carry-over 先を action log に書いてから編集を始めます。

## Default Commands

- `python3 tools/agent_tools/worktree_start.py --current` (legacy cleanup diagnostic only)
- `python3 tools/agent_tools/worktree_scope_lint.py --current`
- `python3 tools/experiments/sync_experiment_registry_context.py --topic <topic> --branch <branch>`
- `python3 tools/agent_tools/work_log.py --kind cleanup --message "<legacy worktree state>" --next "<carry-over or remove>"`
- `python3 tools/agent_tools/work_log.py --kind edit --request-clause-id R1 --message "..." --next "..."`
- `git status --short --branch`
- `git worktree list --porcelain`
- `bash tools/docs/check_worktree_scopes.sh`

## Boundary

- cleanup readiness や delete 可否の review は `worktree-health` を使います。
- artifact の置き場は `agents/canonical/ARTIFACT_PLACEMENT.md` を正本にします。
- repo-wide な routing や CI / Docker review は `comprehensive-development` か `environment-maintenance` を使います。
- Docker / dependency / CI の変更が主題なら `environment-maintenance` を使います。
